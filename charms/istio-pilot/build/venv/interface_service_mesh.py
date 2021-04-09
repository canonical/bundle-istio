from dataclasses import dataclass, asdict
from typing import List

from serialized_data_interface import SerializedDataInterface

SERVICE_MESH_SCHEMA = """
prefix:
  type: string
rewrite:
  type: string
service:
  type: string
port:
  type: number
ingress:
  type: boolean
auth:
  type: object
"""


@dataclass
class Auth:
    request_headers: List[str]
    response_headers: List[str]


class ServiceMeshRequires(SerializedDataInterface):
    def __init__(
        self,
        charm,
        relation_name,
    ):
        super().__init__(charm, relation_name, SERVICE_MESH_SCHEMA, {"v1"}, "requires")

    def add_route(
        self, prefix, service, port, rewrite=None, ingress=False, auth: dict = {}
    ):
        if rewrite is None:
            rewrite = prefix

        # Primitive schema checking
        if auth:
            auth = asdict(Auth(**auth))

        self.send_data(
            {
                "prefix": prefix,
                "rewrite": rewrite,
                "service": service,
                "port": port,
                "ingress": ingress,
                "auth": auth,
            }
        )


class ServiceMeshProvides(SerializedDataInterface):
    def __init__(
        self,
        charm,
        relation_name,
    ):
        super().__init__(charm, relation_name, SERVICE_MESH_SCHEMA, {"v1"}, "provides")

    def routes(self):
        return self.get_data()
