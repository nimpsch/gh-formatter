"""Rule: standardize job id casing and update needs/references."""

from functools import partial

from ruamel.yaml.comments import CommentedMap

from gh_formatter.core.casing import compute_safe_renames
from gh_formatter.core.context import Context
from gh_formatter.core.references import (
    replace_expression_references,
    transform_strings_in_place,
)
from gh_formatter.core.rules.base import BaseRule
from gh_formatter.core.tree import get_map, rename_commented_map_keys

# Expression prefixes under which job ids are referenced. `jobs.<id>` is
# used in reusable workflow outputs (on.workflow_call.outputs.*.value).
JOB_REFERENCE_PREFIXES = ("needs", "jobs")


class JobNamingRule(BaseRule):
    @property
    def id(self) -> str:
        return "job-naming"

    @property
    def description(self) -> str:
        return (
            "Standardize job ID casing and update dependent needs lists "
            "and expressions"
        )

    def should_run(self, context: Context) -> bool:
        return context.file_type == "workflow"

    def apply(self, data: CommentedMap, context: Context) -> None:
        jobs_map = get_map(data, "jobs")
        if jobs_map is None or context.is_ignored(jobs_map):
            return

        renames = compute_safe_renames(
            jobs_map,
            context.config.job_casing,
            context,
            "job",
            preserve_uppercase=context.config.preserve_uppercase_names,
        )
        renames = {
            old: new
            for old, new in renames.items()
            if not context.is_frozen(jobs_map, old)
        }
        if not renames:
            return

        rename_commented_map_keys(jobs_map, renames)
        self._update_needs(jobs_map, renames)

        for old_id, new_id in renames.items():
            transform_strings_in_place(
                data,
                partial(
                    replace_expression_references,
                    prefixes=JOB_REFERENCE_PREFIXES,
                    old_name=old_id,
                    new_name=new_id,
                ),
            )

    @staticmethod
    def _update_needs(jobs_map: CommentedMap, renames: dict[str, str]) -> None:
        """Updates plain `needs:` values (string or list of job ids)."""
        for job_def in jobs_map.values():
            if not isinstance(job_def, CommentedMap) or "needs" not in job_def:
                continue

            needs = job_def["needs"]
            if isinstance(needs, str):
                if needs in renames:
                    job_def["needs"] = renames[needs]
            elif isinstance(needs, list):
                for i, value in enumerate(needs):
                    if value in renames:
                        needs[i] = renames[value]
