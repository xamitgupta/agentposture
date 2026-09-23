"""Microsoft Entra ID: agent identities (service principals) with their granted permissions.

Identity is the most reliable place to find agents: every agent that calls an
API needs a principal. Grant the scanning app ``Application.Read.All`` (application
permission) and admin-consent it. Choose which principals are agents with a tag,
a display-name prefix, or your own OData filter.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterable
from typing import Any

from ..models import Evidence
from . import _http
from .base import Connector, ConnectorError, register

GRAPH = "https://graph.microsoft.com/v1.0"


@register
class EntraIdConnector(Connector):
    type_name = "entra_id"
    evidence_kind = "observed"
    description = "Agent service principals in Microsoft Entra ID with their API permissions and owners."
    options = {"tenant_id": "Directory (tenant) id.", "client_id": "Scanner app id.",
               "client_secret": "Scanner app secret, e.g. env:AZURE_CLIENT_SECRET.",
               "tag": "Only principals carrying this tag (default AIAgent).",
               "name_prefix": "Or: only principals whose display name starts with this.",
               "filter": "Or: a raw Graph OData $filter."}

    def _token(self) -> str:
        tenant = self.option("tenant_id", secret=True)
        if not tenant:
            raise ConnectorError("entra_id source needs tenant_id, client_id and client_secret")
        data = {"client_id": self.option("client_id", secret=True),
                "client_secret": self.option("client_secret", secret=True),
                "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}
        resp = _http.request(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                             headers={"Content-Type": "application/x-www-form-urlencoded"},
                             data=data, method="POST")
        return resp["access_token"]

    def _paged(self, url: str, headers: dict[str, str]) -> Iterable[dict[str, Any]]:
        next_url: str | None = url
        while next_url:
            page = _http.request(next_url, headers=headers)
            yield from page.get("value", [])
            next_url = page.get("@odata.nextLink")

    def discover(self) -> Iterable[Evidence]:
        headers = {"Authorization": f"Bearer {self._token()}", "ConsistencyLevel": "eventual"}
        if self.option("filter"):
            flt = self.option("filter")
        elif self.option("name_prefix"):
            flt = f"startswith(displayName,'{self.option('name_prefix')}')"
        else:
            flt = f"tags/any(t:t eq '{self.option('tag', 'AIAgent')}')"
        url = f"{GRAPH}/servicePrincipals?$count=true&$filter={urllib.parse.quote(flt)}"
        role_cache: dict[str, dict[str, str]] = {}
        for sp in self._paged(url, headers):
            yield self._principal(sp, headers, role_cache)

    def _principal(self, sp: dict[str, Any], headers: dict[str, str],
                   role_cache: dict[str, dict[str, str]]) -> Evidence:
        sid, app_id = sp["id"], sp.get("appId", sp["id"])
        privileges: list[str] = []
        for a in self._paged(f"{GRAPH}/servicePrincipals/{sid}/appRoleAssignments", headers):
            rid = a["resourceId"]
            if rid not in role_cache:
                res = _http.request(f"{GRAPH}/servicePrincipals/{rid}?$select=appRoles,displayName",
                                    headers=headers)
                role_cache[rid] = {r["id"]: r.get("value", "") for r in res.get("appRoles", [])}
                role_cache[rid]["__name"] = res.get("displayName", rid)
            roles = role_cache[rid]
            privileges.append(f"{roles['__name']}:{roles.get(a['appRoleId'], a['appRoleId'])}")
        for g in self._paged(f"{GRAPH}/servicePrincipals/{sid}/oauth2PermissionGrants", headers):
            privileges += [f"delegated:{s}" for s in (g.get("scope") or "").split()]
        owner = None
        for o in self._paged(f"{GRAPH}/servicePrincipals/{sid}/owners", headers):
            owner = o.get("mail") or o.get("userPrincipalName")
            if owner:
                break
        cred = "client_secret" if sp.get("passwordCredentials") else \
            "certificate" if sp.get("keyCredentials") else "federated_or_managed"
        attrs = {
            "name": sp.get("displayName", app_id),
            "description": sp.get("description") or sp.get("notes"),
            "owner": owner,
            "privileges": privileges,
            "identity": app_id,
            "credential_type": cred,
            "exposure": "public" if sp.get("signInAudience") in ("AzureADandPersonalMicrosoftAccount",
                                                                  "PersonalMicrosoftAccount") else None,
            "extra": {"enabled": sp.get("accountEnabled"), "tags": sp.get("tags", [])},
        }
        return self.evidence(app_id, attrs, [f"identity:{app_id}", f"entra:{app_id}"])
