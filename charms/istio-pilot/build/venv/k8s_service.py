from ops.framework import (
    Object,
    StoredState,
    EventBase,
    EventSource,
    ObjectEvents,
)
from operator import attrgetter
from hashlib import md5


class K8sServicesChanged(EventBase):
    pass


class RequireK8sServiceEvents(ObjectEvents):
    k8s_services_changed = EventSource(K8sServicesChanged)


class ProvideK8sService(Object):
    def __init__(self, charm, relation_name, service_name, service_port):
        super().__init__(charm, relation_name)
        # Ensure all related apps are sent the latest data, in case it changed.
        for relation in self.model.relations[relation_name]:
            relation.data[charm.app].update(
                {
                    "service-name": service_name,
                    "service-port": str(service_port),
                }
            )


class RequireK8sService(Object):
    state = StoredState()
    on = RequireK8sServiceEvents()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self._relation_name = relation_name
        self.state.set_default(data_hash=None)
        self.framework.observe(
            charm.on[relation_name].relation_joined, self._check_services
        )
        self.framework.observe(
            charm.on[relation_name].relation_changed, self._check_services
        )

    @property
    def _relations(self):
        return self.model.relations[self._relation_name]

    @property
    def services(self):
        services = []
        for relation in sorted(self._relations, key=attrgetter("id")):
            if not relation.app:
                continue
            service_name = relation.data[relation.app].get("service-name")
            service_port = relation.data[relation.app].get("service-port")
            if service_name and service_port:
                services.append((service_name, service_port))
        return services

    @property
    def is_available(self):
        return len(self.services) > 0

    @property
    def is_created(self):
        return len(self._relations) > 0

    @property
    def _data_hash(self):
        return md5(str(self.services).encode("utf8")).hexdigest()

    def _check_services(self, event):
        if self.is_available and self.state.data_hash != self._data_hash:
            self.state.data_hash = self._data_hash
            self.on.k8s_services_changed.emit()
