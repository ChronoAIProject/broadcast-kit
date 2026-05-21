from __future__ import annotations

from pathlib import Path

from broadcast_kit import publishers
from broadcast_kit.contracts import PLATFORMS, ContractError, read_structured_file, validate_publish_job, validate_publish_result


def run(platform: str, manifest: Path, dry_run: bool, account: str = "default") -> dict:
    if platform not in PLATFORMS - {"all"}:
        raise ContractError(f"platform must be one of {sorted(PLATFORMS - {'all'})}")
    if not manifest.exists():
        raise ContractError(f"manifest does not exist: {manifest}")

    data = read_structured_file(manifest)
    if "publish_job_id" in data:
        validate_publish_job(data, manifest, platform=platform)
    data["_manifest"] = str(manifest)
    config = {"manifest": str(manifest), "account": account}
    result = publishers.publish(platform, data, dry_run=dry_run, config=config)
    validate_publish_result(result)
    return result
