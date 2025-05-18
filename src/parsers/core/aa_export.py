from pathlib import Path

import requests
from app.schemas.common import Region

from ...config import settings
from ...schemas.common import AtlasExportFile, OpenApiInfo
from ...utils import AtlasApi
from ...utils.helper import dump_json, load_json, parse_json_obj_as
from ...utils.log import logger
from ...utils.url import DownUrl
from ...utils.worker import Worker


def update_exported_files(regions: list[Region], force_update: bool):
    if not regions:
        regions = [r for r in Region]

    def _add_download_task(_url, _fp):
        resp = requests.get(_url, headers={"cache-control": "no-cache"})
        resp.raise_for_status()
        Path(_fp).write_bytes(resp.content)
        logger.info(f"{_fp}: update exported file from {_url}")

    fp_openapi = settings.atlas_export_dir / "openapi.json"

    openapi_remote = requests.get(AtlasApi.full_url("openapi.json")).json()
    openapi_local = load_json(fp_openapi)

    api_changed = not openapi_local or parse_json_obj_as(
        OpenApiInfo, openapi_remote["info"]
    ) != parse_json_obj_as(OpenApiInfo, openapi_local["info"])
    if api_changed:
        logger.info(f'API changed:\n{dict(openapi_remote["info"], description="")}')

    for region in Region.__members__.values():
        worker = Worker(f"exported_file_{region}", fake_mode=False)
        fp_info = settings.atlas_export_dir / region.value / "info.json"
        info_local = load_json(fp_info) or {}
        info_remote = DownUrl.export("info.json", region)
        region_changed = (
            region in regions and force_update
        ) or info_local != info_remote

        for f in AtlasExportFile.__members__.values():
            fp_export = f.cache_path(region)
            fp_export.parent.mkdir(parents=True, exist_ok=True)
            if api_changed or region_changed or not fp_export.exists():
                if region not in regions:
                    regions.append(region)
                url = f.resolve_link(region)
                worker.add(_add_download_task, url, fp_export)
            else:
                # logger.info(f'{fp_export}: already updated')
                pass
        worker.wait()
        dump_json(info_remote, fp_info)
        logger.debug(f"Exported files updated:\n{info_remote}")
    dump_json(openapi_remote, fp_openapi)
    return regions
