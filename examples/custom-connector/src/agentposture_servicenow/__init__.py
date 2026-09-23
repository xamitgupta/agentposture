"""Example third-party connector: AI agents recorded as configuration items in ServiceNow.

Install this package next to agentposture and the `servicenow` source type appears:

    pip install -e examples/custom-connector
    agentposture connectors          # lists `servicenow`

It is a template: adjust the table name and the field mapping to your instance.
"""

from __future__ import annotations

import base64
import urllib.parse
from typing import Iterable

from agentposture.connectors import Connector, ConnectorError, register
from agentposture.connectors import _http
from agentposture.models import Evidence


@register
class ServiceNowConnector(Connector):
    type_name = "servicenow"
    evidence_kind = "declared"          # the CMDB is where owners register things
    description = "AI agents recorded as configuration items in a ServiceNow table."
    options = {"instance": "e.g. acme.service-now.com", "table": "CMDB table holding agents",
               "username": "env:SN_USER", "password": "env:SN_PASSWORD",
               "query": "Optional encoded sysparm_query"}

    def discover(self) -> Iterable[Evidence]:
        instance = self.option("instance")
        if not instance:
            raise ConnectorError("servicenow source needs `instance`")
        table = self.option("table", "u_cmdb_ci_ai_agent")
        auth = base64.b64encode(f"{self.option('username', secret=True)}:"
                                f"{self.option('password', secret=True)}".encode()).decode()
        params = {"sysparm_limit": "1000", "sysparm_display_value": "true"}
        if self.option("query"):
            params["sysparm_query"] = self.option("query")
        url = f"https://{instance}/api/now/table/{table}?{urllib.parse.urlencode(params)}"
        rows = _http.request(url, headers={"Authorization": f"Basic {auth}"}).get("result", [])
        for r in rows:
            yield self.evidence(r["sys_id"], {
                "id": r.get("u_agent_id") or r["sys_id"],
                "name": r.get("name"),
                "owner": (r.get("owned_by") or {}).get("email") if isinstance(r.get("owned_by"), dict)
                else r.get("u_owner_email"),
                "team": r.get("support_group") if isinstance(r.get("support_group"), str) else None,
                "lifecycle": r.get("install_status"),
                "business_impact": r.get("business_criticality"),
                "autonomy": r.get("u_autonomy"),
                "exposure": r.get("u_exposure"),
                "data_sensitivity": r.get("u_data_classification"),
            }, [f"identity:{r['u_service_principal']}"] if r.get("u_service_principal") else [])
