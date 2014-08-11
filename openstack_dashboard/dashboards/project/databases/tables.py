# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django.core import urlresolvers
from django.template import defaultfilters as d_filters
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import tables
from horizon.templatetags import sizeformat
from horizon.utils import filters

from openstack_dashboard import api
from openstack_dashboard.dashboards.project.database_backups \
    import tables as backup_tables


ACTIVE_STATES = ("ACTIVE",)


class TerminateInstance(tables.BatchAction):
    name = "terminate"
    action_present = _("Terminate")
    action_past = _("Scheduled termination of %(data_type)s")
    data_type_singular = _("Instance")
    data_type_plural = _("Instances")
    classes = ("ajax-modal",)
    icon = "off"

    def action(self, request, obj_id):
        api.trove.instance_delete(request, obj_id)


class RestartInstance(tables.BatchAction):
    name = "restart"
    action_present = _("Restart")
    action_past = _("Restarted")
    data_type_singular = _("Instance")
    data_type_plural = _("Instances")
    classes = ('btn-danger', 'btn-reboot')

    def allowed(self, request, instance=None):
        return ((instance.status in ACTIVE_STATES
                 or instance.status == 'SHUTOFF'))

    def action(self, request, obj_id):
        api.trove.instance_restart(request, obj_id)


class DeleteUser(tables.DeleteAction):
    name = "delete"
    action_present = _("Delete")
    action_past = _("Deleted")
    data_type_singular = _("User")
    data_type_plural = _("Users")

    def delete(self, request, obj_id):
        datum = self.table.get_object_by_id(obj_id)
        try:
            api.trove.user_delete(request, datum.instance.id, datum.name)
        except Exception:
            msg = _('Error deleting database user.')
            exceptions.handle(request, msg)


class DeleteDatabase(tables.DeleteAction):
    name = "delete"
    action_present = _("Delete")
    action_past = _("Deleted")
    data_type_singular = _("Database")
    data_type_plural = _("Databases")

    def delete(self, request, obj_id):
        datum = self.table.get_object_by_id(obj_id)
        try:
            api.trove.database_delete(request, datum.instance.id, datum.name)
        except Exception:
            msg = _('Error deleting database on instance.')
            exceptions.handle(request, msg)


class LaunchLink(tables.LinkAction):
    name = "launch"
    verbose_name = _("Launch Instance")
    url = "horizon:project:databases:launch"
    classes = ("ajax-modal", "btn-launch")
    icon = "cloud-upload"


class CreateBackup(tables.LinkAction):
    name = "backup"
    verbose_name = _("Create Backup")
    url = "horizon:project:database_backups:create"
    classes = ("ajax-modal",)
    icon = "camera"

    def allowed(self, request, instance=None):
        return (instance.status in ACTIVE_STATES and
                request.user.has_perm('openstack.services.object-store'))

    def get_link_url(self, datam):
        url = urlresolvers.reverse(self.url)
        return url + "?instance=%s" % datam.id


class ResizeVolume(tables.LinkAction):
    name = "resize_volume"
    verbose_name = _("Resize Volume")
    url = "horizon:project:databases:resize_volume"
    classes = ("ajax-modal", "btn-resize")

    def allowed(self, request, instance=None):
        return ((instance.status in ACTIVE_STATES
                 or instance.status == 'SHUTOFF'))

    def get_link_url(self, datum):
        instance_id = self.table.get_object_id(datum)
        return urlresolvers.reverse(self.url, args=[instance_id])


class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, instance_id):
        instance = api.trove.instance_get(request, instance_id)
        try:
            flavor_id = instance.flavor['id']
            instance.full_flavor = api.trove.flavor_get(request, flavor_id)
        except Exception:
            pass
        instance.host = get_host(instance)
        return instance


def get_datastore(instance):
    if hasattr(instance, "datastore"):
        return instance.datastore["type"]
    return _("Not available")


def get_datastore_version(instance):
    if hasattr(instance, "datastore"):
        return instance.datastore["version"]
    return _("Not available")


def get_host(instance):
    if hasattr(instance, "hostname"):
        return instance.hostname
    elif hasattr(instance, "ip") and instance.ip:
        return instance.ip[0]
    return _("Not Assigned")


def get_size(instance):
    if hasattr(instance, "full_flavor"):
        size_string = _("%(name)s | %(RAM)s RAM")
        vals = {'name': instance.full_flavor.name,
                'RAM': sizeformat.mbformat(instance.full_flavor.ram)}
        return size_string % vals
    return _("Not available")


def get_volume_size(instance):
    if hasattr(instance, "volume"):
        return sizeformat.diskgbformat(instance.volume.get("size"))
    return _("Not available")


def get_databases(user):
    if hasattr(user, "access"):
        databases = [db.name for db in user.access]
        databases.sort()
        return ', '.join(databases)
    return _("-")


class InstancesTable(tables.DataTable):
    STATUS_CHOICES = (
        ("active", True),
        ("shutoff", True),
        ("suspended", True),
        ("paused", True),
        ("error", False),
    )
    name = tables.Column("name",
                         link=("horizon:project:databases:detail"),
                         verbose_name=_("Instance Name"))
    datastore = tables.Column(get_datastore,
                              verbose_name=_("Datastore"))
    datastore_version = tables.Column(get_datastore_version,
                                      verbose_name=_("Datastore Version"))
    host = tables.Column(get_host, verbose_name=_("Host"))
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    volume = tables.Column(get_volume_size,
                         verbose_name=_("Volume Size"),
                         attrs={'data-type': 'size'})
    status = tables.Column("status",
                           filters=(d_filters.title,
                                    filters.replace_underscores),
                           verbose_name=_("Status"),
                           status=True,
                           status_choices=STATUS_CHOICES)

    class Meta:
        name = "databases"
        verbose_name = _("Instances")
        status_columns = ["status"]
        row_class = UpdateRow
        table_actions = (LaunchLink, TerminateInstance)
        row_actions = (CreateBackup,
                       ResizeVolume,
                       RestartInstance,
                       TerminateInstance)


class UsersTable(tables.DataTable):
    name = tables.Column("name", verbose_name=_("User Name"))
    host = tables.Column("host", verbose_name=_("Allowed Host"))
    databases = tables.Column(get_databases, verbose_name=_("Databases"))

    class Meta:
        name = "users"
        verbose_name = _("Users")
        table_actions = [DeleteUser]
        row_actions = [DeleteUser]

    def get_object_id(self, datum):
        return datum.name


class DatabaseTable(tables.DataTable):
    name = tables.Column("name", verbose_name=_("Database Name"))

    class Meta:
        name = "databases"
        verbose_name = _("Databases")
        table_actions = [DeleteDatabase]
        row_actions = [DeleteDatabase]

    def get_object_id(self, datum):
        return datum.name


def is_incremental(obj):
    return hasattr(obj, 'parent_id') and obj.parent_id is not None


class InstanceBackupsTable(tables.DataTable):
    name = tables.Column("name",
                         link=("horizon:project:database_backups:detail"),
                         verbose_name=_("Name"))
    created = tables.Column("created", verbose_name=_("Created"),
                            filters=[filters.parse_isotime])
    location = tables.Column(lambda obj: _("Download"),
                             link=lambda obj: obj.locationRef,
                             verbose_name=_("Backup File"))
    incremental = tables.Column(is_incremental,
                                verbose_name=_("Incremental"),
                                filters=(d_filters.yesno,
                                         d_filters.capfirst))
    status = tables.Column("status",
                           filters=(d_filters.title,
                                    filters.replace_underscores),
                           verbose_name=_("Status"),
                           status=True,
                           status_choices=backup_tables.STATUS_CHOICES)

    class Meta:
        name = "backups"
        verbose_name = _("Backups")
        status_columns = ["status"]
        row_class = UpdateRow
        table_actions = (backup_tables.LaunchLink, backup_tables.DeleteBackup)
        row_actions = (backup_tables.RestoreLink, backup_tables.DeleteBackup)
