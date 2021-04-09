from typing import Dict, Optional, Set

import requests
import yaml
from jsonschema import validate
from ops.charm import CharmBase
from ops.framework import Object
from ops.model import Application

__all__ = [
    "NoCompatibleVersions",
    "NoSchemaDefined",
    "NoVersionsListed",
    "get_interfaces",
]


class NoCompatibleVersions(Exception):
    def __init__(self, relation, apps):
        self.relation = relation
        self.apps = ", ".join(apps)

    def __str__(self):
        return f"No compatible {self.relation} versions found for apps: {self.apps}"


class NoSchemaDefined(Exception):
    def __init__(self, end):
        self.end = end

    def __str__(self):
        return (
            f"Calling send_data from the {self.end} end of a relation "
            f"requires defining a {self.end} section in the schema."
        )


class NoVersionsListed(Exception):
    def __init__(self, relation, apps):
        self.relation = relation
        self.apps = ", ".join(apps)

    def __str__(self):
        return f"List of {self.relation} versions not found for apps: {self.apps}"


class SerializedDataInterface(Object):
    """Represents a schema-defined interface between two charms.

    The schema should match the JSON Schema specification, though
    should be written in YAML.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        schema: str,
        versions: Set[str],
        end: str,
    ):
        super().__init__(charm, relation_name)

        for relation in self.model.relations[relation_name]:
            relation.data[charm.app]["_supported_versions"] = yaml.dump(list(versions))

        others = {
            app.name: bag.get("_supported_versions")
            for relation in self.model.relations[relation_name]
            for app, bag in relation.data.items()
            if isinstance(app, Application) and not app._is_our_app
        }

        unversioned = [name for name, versions in others.items() if versions is None]
        if unversioned:
            raise NoVersionsListed(relation_name, unversioned)

        compatibility = {
            name: set.intersection(versions, set(yaml.safe_load(other_versions)))
            for name, other_versions in others.items()
        }
        incompatible = [
            name for name, versions in compatibility.items() if not versions
        ]
        if incompatible:
            raise NoCompatibleVersions(relation_name, incompatible)

        self.charm = charm
        self.relation_name = relation_name
        # Grab the latest compatible API version(s). Assume all version names are in the form of
        # `vX`, where `X` is a potentially multi-digit integer. For example, v1, v2, v12.
        self.versions = {
            name: sorted(vs, key=lambda x: -int(x[1:]))[0]
            for name, vs in compatibility.items()
        }
        self.schema = schema
        self.end = end

    @property
    def _relations(self):
        return [rel for rel in self.model.relations[self.relation_name] if rel.app]

    def get_data(self) -> list:
        other = {
            "provides": "requires",
            "requires": "provides",
        }[self.end]

        data = {
            (relation, app): yaml.safe_load(bag["data"])
            for relation in self._relations
            for app, bag in relation.data.items()
            if isinstance(app, Application) and "data" in bag
        }

        for (rel, app), datum in data.items():
            if datum:
                schema = self.schema[self.versions[rel.app.name]]
                if app._is_our_app:
                    schema = schema[self.end]
                else:
                    schema = schema[other]

                validate(instance=datum, schema=schema)

        return data

    def send_data(self, data: dict):
        data = yaml.dump(data)
        for rel in self._relations:
            try:
                validate(instance=data, schema=self.schema[self.versions[rel.app.name]])
            except KeyError:
                raise NoSchemaDefined(self.end)
            rel.data[self.charm.app]["data"] = data


def _get_schema(schema):
    """Ensures schema is retrieved if necessary, then loads it."""

    if isinstance(schema, str):
        return yaml.safe_load(requests.get(schema).text)

    return schema


def get_interfaces(charm) -> Dict[str, Optional[SerializedDataInterface]]:
    """Reads metadata.yaml to retrieve schema-checked interface objects.

    The returned dictionary will always contain keys for each interface that
    defines a schema, but the associated values may be None, if no relations
    have been made yet on that interface. This is because instantiating the
    SerializedDataInterface class requires agreeing on a schema version by
    both sides of the relation.
    """

    with open("metadata.yaml") as f:
        metadata = yaml.safe_load(f)

    # Ensure we don't have any duplicate keys across both provides and requires
    dupes = set.intersection(
        set(metadata.get("provides", {}).keys()),
        set(metadata.get("requires", {}).keys()),
    )
    assert not dupes, f"Found duplicate keys in provides/requires: {dupes}"

    provides = {
        name: SerializedDataInterface(
            charm,
            name,
            _get_schema(interface["schema"]),
            set(interface["versions"]),
            "provides",
        )
        if charm.model.relations[name]
        else None
        for name, interface in metadata.get("provides", {}).items()
        if "schema" in interface
    }

    requires = {
        name: SerializedDataInterface(
            charm,
            name,
            _get_schema(interface["schema"]),
            set(interface["versions"]),
            "requires",
        )
        if charm.model.relations[name]
        else None
        for name, interface in metadata.get("requires", {}).items()
        if "schema" in interface
    }

    return {**provides, **requires}
