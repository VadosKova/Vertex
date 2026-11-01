from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property


@deconstructible
class EncryptedFileSystemStorage(FileSystemStorage):
    @cached_property
    def base_location(self):
        return str(Path(settings.MEDIA_ROOT) / "private")

    @property
    def _fernet(self):
        return Fernet(settings.FILE_ENCRYPTION_KEY.encode())

    def _save(self, name, content):
        content.seek(0)
        return super()._save(name, ContentFile(self._fernet.encrypt(content.read())))

    def _open(self, name, mode="rb"):
        with super()._open(name, "rb") as fh:
            return ContentFile(self._fernet.decrypt(fh.read()), name=name)


def private_storage():
    return EncryptedFileSystemStorage()