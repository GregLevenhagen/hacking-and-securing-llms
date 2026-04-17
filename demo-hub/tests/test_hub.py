"""Smoke tests for the Demo Hub — landing page, sidebar, and static assets."""

from flask.testing import FlaskClient


class TestLandingPage:
    """Test the hub landing page renders correctly."""

    def test_landing_page_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200

    def test_landing_page_contains_title(self, client: FlaskClient) -> None:
        response = client.get("/")
        html = response.data.decode()
        assert "HACKING" in html
        assert "SECURING" in html

    def test_landing_page_has_all_10_demo_links(self, client: FlaskClient) -> None:
        response = client.get("/")
        html = response.data.decode()
        for i in range(1, 10):
            assert f"/demo-0{i}" in html, f"Missing link for demo-0{i}"
        assert "/demo-10" in html, "Missing link for demo-10"

    def test_landing_page_has_attack_section(self, client: FlaskClient) -> None:
        response = client.get("/")
        html = response.data.decode()
        assert "ATTACK DEMOS" in html

    def test_landing_page_has_defense_section(self, client: FlaskClient) -> None:
        response = client.get("/")
        html = response.data.decode()
        assert "DEFENSE DEMOS" in html

    def test_landing_page_has_keyboard_nav_hint(self, client: FlaskClient) -> None:
        response = client.get("/")
        html = response.data.decode()
        assert "Keyboard" in html


class TestStaticAssets:
    """Test that shared static assets are served correctly."""

    def test_styles_css_loads(self, client: FlaskClient) -> None:
        response = client.get("/static/styles.css")
        assert response.status_code == 200
        assert b"terminal-green" in response.data


class TestDemo09Blueprint:
    """Test that Demo 09 Blueprint is registered and serves correctly."""

    def test_demo_09_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        assert response.status_code == 200

    def test_demo_09_has_approval_gates_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        html = response.data.decode()
        assert "APPROVAL GATES" in html

    def test_demo_09_has_sidebar(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        html = response.data.decode()
        assert "ATTACKS" in html
        assert "DEFENSES" in html

    def test_demo_09_has_quick_actions(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        html = response.data.decode()
        assert "SAFE: calculate" in html
        assert "HIGH: send_email" in html

    def test_demo_09_has_reset_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        html = response.data.decode()
        assert "RESET" in html

    def test_demo_09_api_run_requires_message(self, client: FlaskClient) -> None:
        response = client.post("/demo-09/api/run", json={})
        assert response.status_code == 400

    def test_demo_09_api_approve_handles_missing_id(self, client: FlaskClient) -> None:
        response = client.post("/demo-09/api/approve", json={"request_id": "bogus", "decision": "approve"})
        assert response.status_code == 404

    def test_demo_09_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-09/api/reset", json={})
        assert response.status_code == 200

    def test_demo_09_has_state_persistence_js(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        html = response.data.decode()
        assert "sessionStorage" in html
        assert "demo09_conversation" in html

    def test_demo_09_has_keyboard_shortcuts(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        html = response.data.decode()
        assert "sendDecision" in html
        # A/D keys for approve/deny
        assert "'approve'" in html
        assert "'deny'" in html

    def test_demo_09_has_retry_on_error(self, client: FlaskClient) -> None:
        response = client.get("/demo-09/")
        html = response.data.decode()
        assert "retry" in html


class TestDemo10Blueprint:
    """Test that Demo 10 Blueprint is registered and serves correctly."""

    def test_demo_10_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        assert response.status_code == 200

    def test_demo_10_has_secure_architecture_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "SECURE ARCHITECTURE" in html

    def test_demo_10_has_sidebar(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "ATTACKS" in html
        assert "DEFENSES" in html

    def test_demo_10_has_split_screen_panels(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "VULNERABLE SYSTEM" in html
        assert "SECURED SYSTEM" in html

    def test_demo_10_has_defense_indicators(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "INPUT GUARD" in html
        assert "RETRIEVAL GUARD" in html
        assert "OUTPUT GUARD" in html
        assert "ACTION GUARD" in html

    def test_demo_10_has_attack_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "INJECT:" in html
        assert "ATK-" in html

    def test_demo_10_has_reset_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "RESET" in html

    def test_demo_10_api_scenarios_returns_json(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/api/scenarios")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_demo_10_api_attack_requires_text(self, client: FlaskClient) -> None:
        response = client.post("/demo-10/api/attack", json={})
        assert response.status_code == 400

    def test_demo_10_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-10/api/reset", json={})
        assert response.status_code == 200

    def test_demo_10_has_custom_attack_input(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "custom-attack-input" in html
        assert "custom-attack-form" in html
        assert "custom attack" in html.lower()

    def test_demo_10_has_retry_on_error(self, client: FlaskClient) -> None:
        response = client.get("/demo-10/")
        html = response.data.decode()
        assert "retry" in html


class TestDemo01Blueprint:
    """Test that Demo 01 Blueprint is registered and serves correctly."""

    def test_demo_01_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        assert response.status_code == 200

    def test_demo_01_has_prompt_injection_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "DIRECT PROMPT INJECTION" in html

    def test_demo_01_has_sidebar(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "ATTACKS" in html
        assert "DEFENSES" in html

    def test_demo_01_has_prompt_level_selector(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "Basic Instruction" in html
        assert "Emphatic Instruction" in html
        assert "STRICTNESS" in html

    def test_demo_01_has_payload_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "Classic Override" in html
        assert "Role Switch" in html

    def test_demo_01_has_reset_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "RESET" in html

    def test_demo_01_api_chat_requires_message(self, client: FlaskClient) -> None:
        response = client.post("/demo-01/api/chat", json={})
        assert response.status_code == 400

    def test_demo_01_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-01/api/reset", json={"level": 0})
        assert response.status_code == 200

    def test_demo_01_api_payloads_returns_json(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/api/payloads")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 10

    def test_demo_01_has_state_persistence_js(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "sessionStorage" in html
        assert "demo01_conversation" in html

    def test_demo_01_has_injection_scoring(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "scoreInjection" in html
        assert "INJECTION SCORE" in html


class TestDemo02Blueprint:
    """Test that Demo 02 Blueprint is registered and serves correctly."""

    def test_demo_02_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-02/")
        assert response.status_code == 200

    def test_demo_02_has_indirect_injection_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-02/")
        html = response.data.decode()
        assert "INDIRECT PROMPT INJECTION" in html

    def test_demo_02_has_page_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-02/")
        html = response.data.decode()
        assert "Legitimate Page" in html
        assert "White Font" in html

    def test_demo_02_has_two_panels(self, client: FlaskClient) -> None:
        response = client.get("/demo-02/")
        html = response.data.decode()
        assert "WHAT HUMANS SEE" in html
        assert "WHAT THE LLM SEES" in html

    def test_demo_02_api_analyze_requires_page(self, client: FlaskClient) -> None:
        response = client.post("/demo-02/api/analyze", json={})
        assert response.status_code == 400

    def test_demo_02_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-02/api/reset", json={})
        assert response.status_code == 200


class TestDemo03Blueprint:
    """Test that Demo 03 Blueprint is registered and serves correctly."""

    def test_demo_03_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-03/")
        assert response.status_code == 200

    def test_demo_03_has_rag_poisoning_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-03/")
        html = response.data.decode()
        assert "RAG POISONING" in html

    def test_demo_03_has_phase_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-03/")
        html = response.data.decode()
        assert "BUILD INDEX" in html
        assert "QUERY CLEAN" in html
        assert "POISON INDEX" in html

    def test_demo_03_api_phase_validates_input(self, client: FlaskClient) -> None:
        response = client.post("/demo-03/api/phase", json={"phase": 0})
        assert response.status_code == 400

    def test_demo_03_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-03/api/reset", json={})
        assert response.status_code == 200


class TestDemo04Blueprint:
    """Test that Demo 04 Blueprint is registered and serves correctly."""

    def test_demo_04_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-04/")
        assert response.status_code == 200

    def test_demo_04_has_extraction_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-04/")
        html = response.data.decode()
        assert "SYSTEM PROMPT EXTRACTION" in html

    def test_demo_04_has_known_secrets(self, client: FlaskClient) -> None:
        response = client.get("/demo-04/")
        html = response.data.decode()
        assert "sk-fake-12345" in html

    def test_demo_04_has_run_all_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-04/")
        html = response.data.decode()
        assert "RUN ALL TECHNIQUES" in html

    def test_demo_04_api_chat_requires_message(self, client: FlaskClient) -> None:
        response = client.post("/demo-04/api/chat", json={})
        assert response.status_code == 400

    def test_demo_04_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-04/api/reset", json={})
        assert response.status_code == 200


class TestDemo06Blueprint:
    """Test that Demo 06 Blueprint is registered and serves correctly."""

    def test_demo_06_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-06/")
        assert response.status_code == 200

    def test_demo_06_has_input_sanitization_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-06/")
        html = response.data.decode()
        assert "INPUT SANITIZATION" in html

    def test_demo_06_has_comparison_panels(self, client: FlaskClient) -> None:
        response = client.get("/demo-06/")
        html = response.data.decode()
        assert "VULNERABLE" in html
        assert "DEFENDED" in html

    def test_demo_06_has_payload_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-06/")
        html = response.data.decode()
        assert "Classic Override" in html

    def test_demo_06_has_reset_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-06/")
        html = response.data.decode()
        assert "RESET" in html

    def test_demo_06_api_compare_requires_payload(self, client: FlaskClient) -> None:
        response = client.post("/demo-06/api/compare", json={})
        assert response.status_code == 400

    def test_demo_06_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-06/api/reset", json={})
        assert response.status_code == 200

    def test_demo_06_has_export_results_js(self, client: FlaskClient) -> None:
        response = client.get("/demo-06/")
        html = response.data.decode()
        assert "exportResults" in html
        assert "resultHistory" in html

    def test_demo_06_has_defense_timing_support(self, client: FlaskClient) -> None:
        response = client.get("/demo-06/")
        html = response.data.decode()
        assert "latency_ms" in html


class TestDemo07Blueprint:
    """Test that Demo 07 Blueprint is registered and serves correctly."""

    def test_demo_07_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-07/")
        assert response.status_code == 200

    def test_demo_07_has_rag_defense_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-07/")
        html = response.data.decode()
        assert "RAG DEFENSE" in html

    def test_demo_07_has_comparison_panels(self, client: FlaskClient) -> None:
        response = client.get("/demo-07/")
        html = response.data.decode()
        assert "VULNERABLE" in html
        assert "DEFENDED" in html

    def test_demo_07_has_setup_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-07/")
        html = response.data.decode()
        assert "BUILD INDEX" in html

    def test_demo_07_has_query_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-07/")
        html = response.data.decode()
        assert "refund policy" in html

    def test_demo_07_api_compare_requires_setup(self, client: FlaskClient) -> None:
        response = client.post("/demo-07/api/compare", json={"payload": "test"})
        assert response.status_code == 400

    def test_demo_07_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-07/api/reset", json={})
        assert response.status_code == 200


class TestDemo08Blueprint:
    """Test that Demo 08 Blueprint is registered and serves correctly."""

    def test_demo_08_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-08/")
        assert response.status_code == 200

    def test_demo_08_has_output_validation_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-08/")
        html = response.data.decode()
        assert "OUTPUT VALIDATION" in html

    def test_demo_08_has_comparison_panels(self, client: FlaskClient) -> None:
        response = client.get("/demo-08/")
        html = response.data.decode()
        assert "VULNERABLE" in html
        assert "DEFENDED" in html

    def test_demo_08_has_scenario_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-08/")
        html = response.data.decode()
        assert "API Key Extraction" in html
        assert "Employee SSN" in html

    def test_demo_08_has_reset_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-08/")
        html = response.data.decode()
        assert "RESET" in html

    def test_demo_08_api_compare_requires_payload(self, client: FlaskClient) -> None:
        response = client.post("/demo-08/api/compare", json={})
        assert response.status_code == 400

    def test_demo_08_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-08/api/reset", json={})
        assert response.status_code == 200


class TestDemo05Blueprint:
    """Test that Demo 05 Blueprint is registered and serves correctly."""

    def test_demo_05_index_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        assert response.status_code == 200

    def test_demo_05_has_agent_exploitation_title(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        html = response.data.decode()
        assert "AGENT EXPLOITATION" in html

    def test_demo_05_has_sidebar(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        html = response.data.decode()
        assert "ATTACKS" in html
        assert "DEFENSES" in html

    def test_demo_05_has_exploit_buttons(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        html = response.data.decode()
        assert "Unauthorized File Read" in html
        assert "Data Exfiltration" in html

    def test_demo_05_has_reset_button(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        html = response.data.decode()
        assert "RESET" in html

    def test_demo_05_api_run_requires_message(self, client: FlaskClient) -> None:
        response = client.post("/demo-05/api/run", json={})
        assert response.status_code == 400

    def test_demo_05_api_reset_works(self, client: FlaskClient) -> None:
        response = client.post("/demo-05/api/reset", json={})
        assert response.status_code == 200

    def test_demo_05_has_sensitive_data_highlighting(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        html = response.data.decode()
        assert "highlightSensitive" in html
        assert "SENSITIVE_PATTERNS" in html

    def test_demo_05_has_audit_log(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        html = response.data.decode()
        assert "toolAuditLog" in html
        assert "AUDIT LOG" in html

    def test_demo_05_has_comparison_link(self, client: FlaskClient) -> None:
        response = client.get("/demo-05/")
        html = response.data.decode()
        assert "/demo-09/" in html
        assert "Compare" in html


class TestHealthCheckEndpoint:
    """Test the Ollama health check API endpoint."""

    def test_health_endpoint_exists(self, client: FlaskClient) -> None:
        response = client.get("/api/health")
        # Either 200 (Ollama running) or 503 (not running) — never 404
        assert response.status_code in (200, 503)

    def test_health_returns_json(self, client: FlaskClient) -> None:
        response = client.get("/api/health")
        data = response.get_json()
        assert "ok" in data
        assert isinstance(data["ok"], bool)


class TestFaviconAndPolish:
    """Test favicon, sidebar toggle, and active highlight features."""

    def test_favicon_link_in_head(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert 'rel="icon"' in html
        assert "data:image/svg+xml" in html

    def test_sidebar_has_collapse_toggle(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "sidebar-toggle" in html
        assert "Toggle sidebar" in html

    def test_sidebar_has_escape_key_hint(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "Esc" in html

    def test_ollama_status_present(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "ollama-status" in html

    def test_active_glow_animation_in_styles(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "activeGlow" in html
