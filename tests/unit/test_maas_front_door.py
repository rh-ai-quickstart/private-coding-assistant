"""Helm-render checks for MaaS front-door Gateway, HTTPRoute, and IDE URLs."""

from __future__ import annotations

import subprocess

from helm_pca import (
    AI_SERVING,
    MAAS_HOST,
    PLATFORM,
    REPO_ROOT,
    _authz_istio_route_names,
    _docs,
    _helm_template,
    _httproute,
    _named,
    _rule_first_paths,
)


def test_maas_gateway_allowed_routes_locked():
    rendered = subprocess.run(
        ["helm", "template", "test", str(PLATFORM), "--set", "mcp.enabled=false"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    docs = _docs(rendered)
    gw = _named(docs, "Gateway", "maas-default-gateway")
    assert gw["metadata"]["namespace"] == "openshift-ingress"
    allowed = gw["spec"]["listeners"][0]["allowedRoutes"]["namespaces"]
    assert allowed["from"] == "Selector"
    assert allowed["selector"]["matchLabels"]["pca.ai/allow-maas-routes"] == "true"
    ns = _named(docs, "Namespace", "ai-serving")
    assert ns["metadata"]["labels"]["pca.ai/allow-maas-routes"] == "true"
    dsc = _named(docs, "DataScienceCluster", "default-dsc")
    assert (
        dsc["spec"]["components"]["kserve"]["modelsAsService"]["managementState"]
        == "Managed"
    )
    group = _named(docs, "Group", "pca-developers")
    assert "dev-user1" in group.get("users", [])


def test_existing_openshift_platform_owns_maas_gateway():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(PLATFORM),
            "-f",
            str(REPO_ROOT / "deploy_existing_openshift" / "values-platform-config.yaml"),
            "--set",
            "mcp.enabled=false",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    docs = _docs(rendered)
    gw = _named(docs, "Gateway", "maas-default-gateway")
    assert gw["metadata"]["namespace"] == "openshift-ingress"
    kinds = {d.get("kind") for d in docs}
    assert "DataScienceCluster" not in kinds


def test_maas_crs_and_no_gateway_when_ai_gateway_disabled():
    rendered = _helm_template(AI_SERVING, ["--set", "tlsJob.enabled=false"])
    docs = _docs(rendered)
    ref = _named(docs, "MaaSModelRef", "pca-auto")
    assert ref["apiVersion"] == "maas.opendatahub.io/v1alpha1"
    assert ref["spec"]["modelRef"]["kind"] == "LLMInferenceService"
    assert ref["spec"]["modelRef"]["name"] == "qwen3-coder"
    sub = _named(docs, "MaaSSubscription", "pca-ide")
    assert sub["apiVersion"] == "maas.opendatahub.io/v1alpha1"
    assert sub["spec"]["owner"]["groups"] == [{"name": "pca-developers"}]
    auth = _named(docs, "MaaSAuthPolicy", "pca-ide")
    assert auth["apiVersion"] == "maas.opendatahub.io/v1alpha1"
    kinds_names = {(d.get("kind"), d.get("metadata", {}).get("name")) for d in docs}
    assert ("Gateway", "pca-ai-gateway") not in kinds_names
    assert ("Gateway", "maas-default-gateway") not in kinds_names


def test_maas_crs_use_variant_helper_for_qwen38():
    rendered = _helm_template(
        AI_SERVING,
        ["--set", "tlsJob.enabled=false", "--set", "model.variant=qwen3.8"],
    )
    docs = _docs(rendered)
    ref = _named(docs, "MaaSModelRef", "pca-auto")
    assert ref["spec"]["modelRef"]["name"] == "qwen3-8-coder"
    assert _named(docs, "LLMInferenceService", "qwen3-8-coder")


def test_maas_gateway_created_when_flag_set():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(PLATFORM),
            "--set",
            "mcp.enabled=false",
            "--set",
            "clusterConfig.enabled=false",
            "--set",
            "maas.gateway.create=true",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    gw = _named(_docs(rendered), "Gateway", "maas-default-gateway")
    assert gw["metadata"]["namespace"] == "openshift-ingress"
    assert gw["spec"]["listeners"][0]["allowedRoutes"]["namespaces"]["from"] == "Selector"
    assert gw["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    models_ns = _named(_docs(rendered), "Namespace", "models-as-a-service")
    assert models_ns["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"


def test_maas_httproute_sets_hostname_when_configured():
    rendered = _helm_template(
        AI_SERVING,
        [
            "--set",
            "tlsJob.enabled=false",
            "--set",
            "maas.hostname=maas.apps.example.com",
        ],
    )
    docs = _docs(rendered)
    route = _named(docs, "HTTPRoute", "pca-maas-front-door")
    assert route["spec"]["hostnames"] == ["maas.apps.example.com"]
    ref = _named(docs, "MaaSModelRef", "pca-auto")
    assert ref["spec"]["endpointOverride"] == "https://maas.apps.example.com/v1"
    filt = _named(docs, "EnvoyFilter", "pca-maas-models-first")
    vhost = filt["spec"]["configPatches"][0]["match"]["routeConfiguration"]["vhost"]
    assert vhost["name"] == "maas.apps.example.com:443"
    authz = _named(docs, "EnvoyFilter", "pca-maas-authorino-check")
    assert authz["metadata"]["namespace"] == "openshift-ingress"
    patches = authz["spec"]["configPatches"]
    cluster = next(p for p in patches if p.get("applyTo") == "CLUSTER")
    assert cluster["patch"]["value"]["name"] == "pca-authorino-grpc"
    assert "transport_socket" not in cluster["patch"]["value"]
    assert cluster["patch"]["value"]["load_assignment"]["endpoints"][0][
        "lb_endpoints"
    ][0]["endpoint"]["address"]["socket_address"] == {
        "address": "authorino-authorino-authorization.kuadrant-system.svc.cluster.local",
        "port_value": 50051,
    }
    http_filter = next(p for p in patches if p.get("applyTo") == "HTTP_FILTER")
    assert http_filter["patch"]["value"]["disabled"] is True
    assert http_filter["match"]["listener"]["filterChain"]["sni"] == "maas.apps.example.com"
    route_names = [
        p["match"]["routeConfiguration"]["vhost"]["route"]["name"]
        for p in patches
        if p.get("applyTo") == "HTTP_ROUTE"
    ]
    assert route_names == _authz_istio_route_names()
    for p in patches:
        if p.get("applyTo") != "HTTP_ROUTE":
            continue
        tfc = p["patch"]["value"]["typed_per_filter_config"]
        assert tfc["envoy.filters.http.ext_authz"]["disabled"] is False
        assert tfc["envoy.filters.http.ext_proc.bbr"]["disabled"] is True
        wasm = "extensions.istio.io/wasmplugin/openshift-ingress.kuadrant-maas-default-gateway"
        assert tfc[wasm]["disabled"] is True
    ac = _named(docs, "AuthConfig", "pca-maas-envoy-apikey")
    assert ac["spec"]["hosts"] == ["maas.apps.example.com"]
    auth_ids = (ac["spec"].get("authentication") or {})
    assert "pca-maas-apikey" in auth_ids
    assert "pca-ai-gateway-apikey" not in auth_ids


def test_kuadrant_authorino_stays_plaintext_with_envoyfilter():
    """EnvoyFilter ext_authz is plaintext. Kuadrant must not TLS-wrap Authorino."""
    rendered = _helm_template(
        AI_SERVING,
        [
            "-f",
            str(REPO_ROOT / "deploy_existing_openshift" / "values-ai-serving.yaml"),
            "--set",
            "tlsJob.enabled=false",
        ],
    )
    docs = _docs(rendered)
    kuadrant = _named(docs, "Kuadrant", "kuadrant")
    assert kuadrant["spec"]["mtls"]["authorino"] is False
    assert kuadrant["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    k_ns = _named(docs, "Namespace", "kuadrant-system")
    assert k_ns["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    authz = _named(docs, "EnvoyFilter", "pca-maas-authorino-check")
    cluster = next(
        p for p in authz["spec"]["configPatches"] if p.get("applyTo") == "CLUSTER"
    )
    assert "transport_socket" not in cluster["patch"]["value"]


def test_maas_empty_hostname_agrees_on_catchall_vhost():
    """HTTPRoute / AuthConfig / EnvoyFilter must not pin cluster FQDN when hostname is unset."""
    rendered = _helm_template(
        AI_SERVING,
        [
            "-f",
            str(REPO_ROOT / "deploy_existing_openshift" / "values-ai-serving.yaml"),
            "--set",
            "tlsJob.enabled=false",
            "--set",
            "maas.hostname=",
        ],
    )
    docs = _docs(rendered)
    route = _httproute(docs)
    assert not route["spec"].get("hostnames")
    assert _rule_first_paths(route) == [
        "/v1/chat/completions",
        "/local/v1",
        "/v1/models",
        "/v1",
    ]

    ac = _named(docs, "AuthConfig", "pca-maas-envoy-apikey")
    ac_hosts = ac["spec"]["hosts"]
    assert ac_hosts != [MAAS_HOST]
    assert MAAS_HOST not in ac_hosts
    assert ac_hosts == ["*:443"]

    authz = _named(docs, "EnvoyFilter", "pca-maas-authorino-check")
    patches = authz["spec"]["configPatches"]
    http_filter = next(p for p in patches if p.get("applyTo") == "HTTP_FILTER")
    assert http_filter["patch"]["value"]["disabled"] is True
    listener = http_filter["match"]["listener"]
    assert listener["portNumber"] == 443
    chain = listener.get("filterChain") or {}
    assert "sni" not in chain
    assert chain.get("sni") != MAAS_HOST

    route_patches = [p for p in patches if p.get("applyTo") == "HTTP_ROUTE"]
    assert [p["match"]["routeConfiguration"]["vhost"]["name"] for p in route_patches] == [
        "*:443",
        "*:443",
        "*:443",
    ]
    assert [
        p["match"]["routeConfiguration"]["vhost"]["route"]["name"] for p in route_patches
    ] == _authz_istio_route_names()
    for patch in route_patches:
        tfc = patch["patch"]["value"]["typed_per_filter_config"]
        ext = tfc["envoy.filters.http.ext_authz"]
        assert "disabled" not in ext
        assert ext["check_settings"]["context_extensions"]["host"] == "*:443"
        assert tfc["envoy.filters.http.ext_proc.bbr"]["disabled"] is True
        wasm = "extensions.istio.io/wasmplugin/openshift-ingress.kuadrant-maas-default-gateway"
        assert tfc[wasm]["disabled"] is True

    models = _named(docs, "EnvoyFilter", "pca-maas-models-first")
    models_vhost = models["spec"]["configPatches"][0]["match"]["routeConfiguration"][
        "vhost"
    ]
    assert models_vhost["name"] == "*:443"
    assert models_vhost["name"] != f"{MAAS_HOST}:443"
