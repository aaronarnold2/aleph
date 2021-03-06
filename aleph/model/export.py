import logging
from datetime import datetime, timedelta
from pathlib import Path

from normality import stringify, safe_filename
from flask_babel import lazy_gettext
from sqlalchemy.dialects.postgresql import JSONB
from servicelayer.archive.util import checksum, ensure_path
from servicelayer.cache import make_key

from aleph.core import db, archive
from aleph.model import Role, Collection
from aleph.model.common import IdModel, DatedModel

log = logging.getLogger(__name__)


class Export(db.Model, IdModel, DatedModel):
    """A data export run in the background. The data is stored in a cloud
    storage bucket and the user is given a link to download the data. The link
    expires after a fixed duration and the exported data is deleted. """

    MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB
    STATUS_PENDING = "pending"
    STATUS_SUCCESSFUL = "successful"
    STATUS_FAILED = "failed"
    EXPORT_STATUS = {
        STATUS_PENDING: lazy_gettext("pending"),
        STATUS_SUCCESSFUL: lazy_gettext("successful"),
        STATUS_FAILED: lazy_gettext("failed"),
    }
    DEFAULT_STATUS = STATUS_PENDING
    DEFAULT_EXPIRATION = timedelta(days=30)  # After 30 days

    label = db.Column(db.Unicode)

    operation = db.Column(db.Unicode)

    creator_id = db.Column(db.Integer, db.ForeignKey("role.id"))
    creator = db.relationship(Role, backref=db.backref("exports", lazy="dynamic"))
    collection_id = db.Column(
        db.Integer, db.ForeignKey("collection.id"), index=True, nullable=True
    )
    collection = db.relationship(
        Collection, backref=db.backref("exports", lazy="dynamic")
    )

    expires_at = db.Column(db.DateTime, default=None, nullable=True)
    deleted = db.Column(db.Boolean, default=False)
    export_status = db.Column(db.Unicode, default=DEFAULT_STATUS)

    content_hash = db.Column(db.Unicode(65), index=True, nullable=True)
    file_size = db.Column(db.BigInteger, nullable=True)  # In bytes
    file_name = db.Column(db.Unicode, nullable=True)
    mime_type = db.Column(db.Unicode)
    meta = db.Column(JSONB, default={})

    def to_dict(self):
        data = self.to_dict_dates()
        if self.export_status in self.EXPORT_STATUS:
            data["export_status"] = self.EXPORT_STATUS.get(self.export_status)
        data.update(
            {
                "id": stringify(self.id),
                "label": self.label,
                "operation": self.operation,
                "creator_id": stringify(self.creator_id),
                "collection_id": self.collection_id,
                "expires_at": self.expires_at,
                "deleted": self.deleted,
                "export_status": self.export_status,
                "content_hash": self.content_hash,
                "file_size": self.file_size,
                "file_name": self.file_name,
                "meta": self.meta,
            }
        )
        return data

    @classmethod
    def create(
        cls,
        operation,
        role_id,
        label,
        file_path=None,
        expires_after=None,
        collection=None,
        mime_type=None,
    ):
        export = cls()
        export.creator_id = role_id
        export.operation = operation
        export.label = label
        if file_path is not None:
            export.set_filepath(file_path)
        if collection is not None:
            export.collection_id = collection.id
        export.mime_type = mime_type
        export.expires_at = datetime.utcnow() + (
            expires_after or cls.DEFAULT_EXPIRATION
        )
        db.session.add(export)
        return export

    @property
    def namespace(self):
        return make_key("role", self.creator_id)

    def publish(self):
        if not self._file_path:
            raise RuntimeError("file path not present for export: %r", self)
        # Use contenthash as filename to make to ensure uniqueness
        path = Path(self._file_path.parent, self.content_hash)
        self._file_path.rename(path)
        try:
            archive.publish(self.namespace, path, self.mime_type)
            self.set_status(status=Export.STATUS_SUCCESSFUL)
        except Exception as ex:
            self.set_status(status=Export.STATUS_FAILED)
            raise ex

    def set_filepath(self, file_path):
        file_path = ensure_path(file_path)
        file_name = safe_filename(file_path)
        file_size = file_path.stat().st_size
        self.file_name = file_name
        self.file_size = file_size
        self._file_path = file_path
        self.content_hash = checksum(file_path)

    def set_status(self, status):
        if status in self.EXPORT_STATUS:
            self.export_status = status
            db.session.add(self)

    def delete_publication(self):
        if self._should_delete_publication():
            archive.delete_publication(self.namespace, self.content_hash)
        self.deleted = True
        db.session.add(self)

    def _should_delete_publication(self):
        """Check whether the published export should be deleted from the archive

        Since we store exports by contenthash, there may be other non-expired exports
        that point to the same file in the archive"""
        q = (
            Export.all()
            .filter(Export.content_hash == self.content_hash)
            .filter(Export.deleted.isnot(True))
            .filter(Export.id != self.id)
        )
        return q.first() is None

    @classmethod
    def get_expired(cls, deleted=False):
        now = datetime.utcnow()
        q = cls.all().filter(cls.expires_at.isnot(None)).filter(cls.expires_at <= now)
        if deleted is not None:
            q = q.filter(cls.deleted == deleted)
        return q

    @classmethod
    def by_id(cls, id, role_id=None, deleted=False):
        q = cls.all().filter_by(id=id)
        if role_id is not None:
            q = q.filter(cls.creator_id == role_id)
        if not deleted:
            q = q.filter(cls.deleted == False)
        return q.first()

    @classmethod
    def by_role_id(cls, role_id, deleted=False):
        q = cls.all()
        q = q.filter(cls.creator_id == role_id)
        if not deleted:
            q = q.filter(cls.deleted == False)
        q = q.order_by(cls.created_at.desc())
        return q

    def __repr__(self):
        return "<Export(%r, %r)>" % (self.id, self.creator_id)
