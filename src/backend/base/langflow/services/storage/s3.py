from __future__ import annotations

from typing import TYPE_CHECKING

import aioboto3
from botocore.exceptions import ClientError
from lfx.log.logger import logger

from .service import StorageService

if TYPE_CHECKING:
    from lfx.services.settings.service import SettingsService

    from langflow.services.session.service import SessionService


class S3StorageService(StorageService):
    """A service class for handling S3 storage operations with multi-tenant isolation."""

    def __init__(
        self,
        session_service: SessionService,
        settings_service: SettingsService,
        bucket_name: str,
        region_name: str = "ap-northeast-1",
    ) -> None:
        """Initialize the S3 storage service.

        Args:
            session_service: Session service instance.
            settings_service: Settings service instance.
            bucket_name: S3 bucket name for file storage.
            region_name: AWS region name (default: ap-northeast-1).
        """
        super().__init__(session_service, settings_service)
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.session = aioboto3.Session()
        self.set_ready()

    def build_full_path(self, flow_id: str, file_name: str, schema_name: str | None = None) -> str:
        """Build the full S3 key path with optional schema prefix.

        Args:
            flow_id: The identifier for the flow (typically user_id).
            file_name: The name of the file.
            schema_name: Optional schema name for multi-tenant isolation.

        Returns:
            S3 key path string.
        """
        if schema_name:
            # Multi-tenant: {schema}/{user_id}/{filename}
            return f"{schema_name}/{flow_id}/{file_name}"
        # Legacy/single-tenant: {user_id}/{filename}
        return f"{flow_id}/{file_name}"

    async def save_file(self, flow_id: str, file_name: str, data: bytes, schema_name: str | None = None) -> None:
        """Save a file to S3.

        Args:
            flow_id: The identifier for the flow.
            file_name: The name of the file to be saved.
            data: The byte content of the file.
            schema_name: Optional schema name for multi-tenant isolation.

        Raises:
            Exception: If S3 upload fails.
        """
        s3_key = self.build_full_path(flow_id, file_name, schema_name)

        try:
            async with self.session.client("s3", region_name=self.region_name) as s3_client:
                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=data,
                    ServerSideEncryption="AES256",  # Enable encryption at rest
                )
            await logger.ainfo(f"File {file_name} saved successfully to S3 in flow {flow_id}.")
        except ClientError as e:
            await logger.aerror(f"S3 ClientError saving file {file_name} in flow {flow_id}: {e}")
            raise
        except Exception:
            logger.exception(f"Error saving file {file_name} to S3 in flow {flow_id}")
            raise

    async def get_file(self, flow_id: str, file_name: str, schema_name: str | None = None) -> bytes:
        """Retrieve a file from S3.

        Args:
            flow_id: The identifier for the flow.
            file_name: The name of the file to be retrieved.
            schema_name: Optional schema name for multi-tenant isolation.

        Returns:
            The byte content of the file.

        Raises:
            FileNotFoundError: If the file does not exist in S3.
        """
        s3_key = self.build_full_path(flow_id, file_name, schema_name)

        try:
            async with self.session.client("s3", region_name=self.region_name) as s3_client:
                response = await s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
                content = await response["Body"].read()

            logger.debug(f"File {file_name} retrieved successfully from S3 flow {flow_id}.")
            return content
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                await logger.awarning(f"File {file_name} not found in S3 flow {flow_id}.")
                msg = f"File {file_name} not found in flow {flow_id}"
                raise FileNotFoundError(msg) from e
            await logger.aerror(f"S3 ClientError retrieving file {file_name} in flow {flow_id}: {e}")
            raise
        except Exception:
            logger.exception(f"Error retrieving file {file_name} from S3 flow {flow_id}")
            raise

    async def list_files(self, flow_id: str, schema_name: str | None = None) -> list[str]:
        """List all files in a specified flow from S3.

        Args:
            flow_id: The identifier for the flow.
            schema_name: Optional schema name for multi-tenant isolation.

        Returns:
            A list of file names.
        """
        if not isinstance(flow_id, str):
            flow_id = str(flow_id)

        # Build prefix for listing objects
        if schema_name:
            prefix = f"{schema_name}/{flow_id}/"
        else:
            prefix = f"{flow_id}/"

        files = []
        try:
            async with self.session.client("s3", region_name=self.region_name) as s3_client:
                paginator = s3_client.get_paginator("list_objects_v2")
                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                    if "Contents" in page:
                        for obj in page["Contents"]:
                            # Extract filename from full key path
                            key = obj["Key"]
                            # Remove prefix to get just the filename
                            if key.startswith(prefix):
                                file_name = key[len(prefix) :]
                                # Only include direct children, not files in subdirectories
                                if "/" not in file_name and file_name:
                                    files.append(file_name)

            await logger.ainfo(f"Listed {len(files)} files in S3 flow {flow_id}.")
            return files
        except ClientError as e:
            await logger.aerror(f"S3 ClientError listing files in flow {flow_id}: {e}")
            raise
        except Exception:
            logger.exception(f"Error listing files from S3 flow {flow_id}")
            raise

    async def delete_file(self, flow_id: str, file_name: str, schema_name: str | None = None) -> None:
        """Delete a file from S3.

        Args:
            flow_id: The identifier for the flow.
            file_name: The name of the file to be deleted.
            schema_name: Optional schema name for multi-tenant isolation.
        """
        s3_key = self.build_full_path(flow_id, file_name, schema_name)

        try:
            async with self.session.client("s3", region_name=self.region_name) as s3_client:
                # Check if file exists first
                try:
                    await s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
                except ClientError as e:
                    if e.response["Error"]["Code"] == "404":
                        await logger.awarning(f"Attempted to delete non-existent file {file_name} in flow {flow_id}.")
                        return
                    raise

                # Delete the object
                await s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                await logger.ainfo(f"File {file_name} deleted successfully from S3 flow {flow_id}.")
        except ClientError as e:
            await logger.aerror(f"S3 ClientError deleting file {file_name} in flow {flow_id}: {e}")
            raise
        except Exception:
            logger.exception(f"Error deleting file {file_name} from S3 flow {flow_id}")
            raise

    async def get_file_size(self, flow_id: str, file_name: str, schema_name: str | None = None) -> int:
        """Get the size of a file in S3.

        Args:
            flow_id: The identifier for the flow.
            file_name: The name of the file.
            schema_name: Optional schema name for multi-tenant isolation.

        Returns:
            File size in bytes.

        Raises:
            FileNotFoundError: If the file does not exist in S3.
        """
        s3_key = self.build_full_path(flow_id, file_name, schema_name)

        try:
            async with self.session.client("s3", region_name=self.region_name) as s3_client:
                response = await s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
                file_size = response["ContentLength"]

            logger.debug(f"File {file_name} size retrieved from S3 flow {flow_id}: {file_size} bytes")
            return file_size
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                await logger.awarning(f"File {file_name} not found in S3 flow {flow_id}.")
                msg = f"File {file_name} not found in flow {flow_id}"
                raise FileNotFoundError(msg) from e
            await logger.aerror(f"S3 ClientError getting file size for {file_name} in flow {flow_id}: {e}")
            raise
        except Exception:
            logger.exception(f"Error getting file size for {file_name} from S3 flow {flow_id}")
            raise

    async def teardown(self) -> None:
        """Perform any cleanup operations when the service is being torn down."""
        # aioboto3 sessions are context-managed, no explicit cleanup needed
        await logger.ainfo("S3 storage service teardown completed.")
