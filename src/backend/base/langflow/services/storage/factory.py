from lfx.log.logger import logger
from lfx.services.settings.service import SettingsService
from typing_extensions import override

from langflow.services.factory import ServiceFactory
from langflow.services.session.service import SessionService
from langflow.services.storage.service import StorageService


class StorageServiceFactory(ServiceFactory):
    def __init__(self) -> None:
        super().__init__(
            StorageService,
        )

    @override
    def create(self, session_service: SessionService, settings_service: SettingsService):
        storage_type = settings_service.settings.storage_type
        if storage_type.lower() == "local":
            from .local import LocalStorageService

            return LocalStorageService(session_service, settings_service)
        if storage_type.lower() == "s3":
            from .s3 import S3StorageService

            bucket_name = settings_service.settings.s3_bucket_name
            if not bucket_name:
                msg = "S3 storage type requires LANGFLOW_S3_BUCKET_NAME to be set"
                raise ValueError(msg)

            region_name = settings_service.settings.s3_region_name
            return S3StorageService(
                session_service=session_service,
                settings_service=settings_service,
                bucket_name=bucket_name,
                region_name=region_name,
            )
        logger.warning(f"Storage type {storage_type} not supported. Using local storage.")
        from .local import LocalStorageService

        return LocalStorageService(session_service, settings_service)
