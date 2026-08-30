import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine
from app.evals.cases import EVAL_CASES, EvalCase
from app.evals.graders import (
    EvalTrace,
    GraderResult,
    IdempotencyGrader,
    OutcomeGrader,
    PolicyComplianceGrader,
    TrajectoryGrader,
    trace_payload,
)
from app.llm.mock import MockLLMProvider
from app.models import RunStatus, ServiceState
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.services.agent_loop import AgentRunner
from app.services.approvals import ApprovalService

GRADERS = (OutcomeGrader(), TrajectoryGrader(), PolicyComplianceGrader(), IdempotencyGrader())


@dataclass(frozen=True)
class CaseEvaluation:
    case: EvalCase
    trace: EvalTrace
    graders: tuple[GraderResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.graders)

    def as_dict(self) -> dict[str, object]:
        return {
            "case": self.case.name,
            "passed": self.passed,
            "score": sum(result.score for result in self.graders),
            "max_score": len(self.graders),
            "graders": [result.as_dict() for result in self.graders],
            "trace": trace_payload(self.trace),
        }


async def run_case(case: EvalCase) -> CaseEvaluation:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        for seed in case.initial_services:
            session.add(
                ServiceState(
                    service=seed.service,
                    health=seed.health,
                    restart_count=seed.restart_count,
                )
            )
        session.commit()

        runner = AgentRunner(
            session,
            provider=MockLLMProvider(),
            provider_name="mock",
            model="mock-operations-agent",
            max_steps=8,
            run_timeout_seconds=10,
        )
        run_id = await runner.start_run(case.user_request)
        run = RunRepository(session).get(run_id)
        if run is None:
            raise RuntimeError(f"eval case {case.name} did not create a run")

        if run.status is RunStatus.WAITING_APPROVAL:
            if case.approval is None:
                pass
            else:
                pending = [
                    action
                    for action in ActionRepository(session).list_for_run(run_id)
                    if action.status.value == "pending_approval"
                ]
                if len(pending) != 1:
                    raise RuntimeError(
                        f"eval case {case.name} expected one pending approval, got {len(pending)}"
                    )
                approval_service = ApprovalService(session, runner=runner)
                if case.approval == "approve":
                    await approval_service.approve(pending[0].id, "eval-runner")
                else:
                    await approval_service.deny(pending[0].id, "eval-runner")

        final_run = RunRepository(session).get(run_id)
        if final_run is None:
            raise RuntimeError(f"eval case {case.name} lost its run")
        services: list[ServiceState] = []
        for seed in case.initial_services:
            service = session.get(ServiceState, seed.service)
            if service is not None:
                services.append(service)
        trace = EvalTrace(
            run=final_run,
            actions=tuple(ActionRepository(session).list_for_run(run_id)),
            audit_events=tuple(AuditRepository(session).list(run_id)),
            services=tuple(services),
        )
        graders = tuple(grader.grade(case, trace) for grader in GRADERS)
        return CaseEvaluation(case=case, trace=trace, graders=graders)


async def run_all(cases: tuple[EvalCase, ...] = EVAL_CASES) -> tuple[CaseEvaluation, ...]:
    return tuple([await run_case(case) for case in cases])


def write_results(
    results: tuple[CaseEvaluation, ...], path: Path = Path("eval-results.json")
) -> None:
    payload = {
        "passed": all(result.passed for result in results),
        "cases": [result.as_dict() for result in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_summary(results: tuple[CaseEvaluation, ...]) -> None:
    print("case                                      score   status")
    print("-------------------------------------------------------")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{result.case.name:<42} {sum(item.score for item in result.graders)}/4     {status}")
        if not result.passed:
            for grader in result.graders:
                if not grader.passed:
                    print(f"  - {grader.name}: {grader.message}")


def main() -> int:
    results = asyncio.run(run_all())
    write_results(results)
    print_summary(results)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
