"""Live named-account checks. Optional synthetic analysis and referral lifecycle."""
import argparse
import json
import re
from contextlib import ExitStack
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def credentials():
    text = (ROOT / "data/portal-accounts.txt").read_text(encoding="utf-8")
    result = {name.strip(): password for name, password in re.findall(r"Kullanıcı adı: ([^\n]+)\nParola: ([^\n]+)", text)}
    if result.get("ihtiyac_admin", "").startswith("Önceki"):
        result["ihtiyac_admin"] = (ROOT / "data/admin-access.txt").read_text(encoding="utf-8").split("Parola: ", 1)[1].splitlines()[0]
    return result


def checked(response):
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exercise", action="store_true", help="Create one clearly synthetic request and exercise routing.")
    args = parser.parse_args()
    with ExitStack() as stack:
        clients = {name: stack.enter_context(httpx.Client(base_url="http://127.0.0.1:8000", timeout=180)) for name in credentials()}
        guest = stack.enter_context(httpx.Client(base_url="http://127.0.0.1:8000", timeout=20))
        denied = {path: guest.get(path).status_code for path in ("/api/admin/requests", "/api/requests/mine", "/api/documents/status", "/api/health")}
        assert all(code == 401 for code in denied.values())
        roles = {}
        try:
            for name, password in credentials().items():
                reply = checked(clients[name].post("/api/auth/login", json={"username": name, "password": password}))
                roles[name] = reply["user"]["role"]
            employee, analyst, technical, engineering = [clients[name] for name in ("calisan", "ihtiyac_admin", "teknik_admin", "muhendislik_admin")]
            for designer in (technical, engineering):
                assert designer.get("/api/documents/status").status_code == 403
            inventory = checked(analyst.get("/api/documents/status"))
            assert inventory["complete"] and inventory["error_count"] == 0
            report = {"guest_denied": denied, "roles": roles, "ready_pdfs": inventory["ready_count"],
                      "before_total": checked(analyst.get("/api/admin/requests"))["total"]}
            inspected = 0
            while inspected < report["before_total"]:
                page = checked(analyst.get("/api/admin/requests", params={"limit": 100, "offset": inspected}))
                assert page["items"], "Request listing ended before the recorded total"
                for item in page["items"]:
                    detail = checked(analyst.get(f"/api/admin/requests/{item['request_id']}"))
                    assert detail["request_id"] == item["request_id"]
                    assert "analysis_state" in detail
                inspected += len(page["items"])
            report["existing_details_opened"] = inspected
            report['operations'] = {}
            for name, client in clients.items():
                inbox = checked(client.get('/api/operations/inbox'))
                notices = checked(client.get('/api/operations/notifications/count'))
                delegations = checked(client.get('/api/operations/delegations'))
                assert all(item['required_actions'] for item in inbox['items'])
                report['operations'][name] = {'inbox_total': inbox['total'], 'unread': notices['unread_count'],
                                             'eligible_delegates': len(delegations['options'])}
            if args.exercise:
                request = checked(employee.post("/api/requests/analyze", json={"text":
                    "Sentetik hesap ve rol akışı doğrulaması: Excel dosyalarını Power Query ile birleştirme ve Pivot tablolarla raporlama eğitimi istiyorum. Bu kayıt yalnızca yazılım testi içindir."}))
                identifier = request["request_id"]
                path = f"/api/admin/requests/{identifier}"
                for designer in (technical, engineering):
                    assert designer.get(path).status_code == 404
                referral = {"department": "TECHNICAL_DESIGN", "training_need_confirmed": True, "expected_version": 1,
                            "analysis_summary": "Sentetik rol testi: eğitim ihtiyacı doğrulandı; teknik araç kullanımı için eğitim tasarımı isteniyor."}
                result = checked(analyst.post(path + "/refer", json=referral))
                assert technical.get(path).status_code == 200 and engineering.get(path).status_code == 404
                result = checked(technical.patch(path + "/status", json={"status": "ACTION_PLANNED",
                    "note": "Sentetik teknik tasarım iş akışı kontrol edildi.", "expected_version": result["version"]}))
                result = checked(technical.patch(path + "/status", json={"status": "IN_REVIEW",
                    "note": "Sentetik geri gönderme testi: kapsam tekrar analiz edilecek.", "expected_version": result["version"]}))
                assert technical.get(path).status_code == 404
                referral.update(department="ENGINEERING_DESIGN", expected_version=result["version"],
                    analysis_summary="Sentetik mühendislik yönlendirme testi; gerçek bir eğitim görevlendirmesi değildir.")
                result = checked(analyst.post(path + "/refer", json=referral))
                assert technical.get(path).status_code == 404 and engineering.get(path).status_code == 200
                for status in ("IN_REVIEW", "REFERRED", "RESOLVED", "NEEDS_INFO", "ACTION_PLANNED"):
                    filtered = checked(analyst.get("/api/admin/requests", params={"status": status}))
                    assert all(item["status"] == status for item in filtered["items"])
                visible = checked(employee.get(f"/api/requests/{identifier}"))
                assert visible["referral"]["department"] == "ENGINEERING_DESIGN"
                report.update(test_request_id=identifier, fit=request["coverage"]["fit_percent"],
                              routing="before-denied, technical-only, returned-hidden, engineering-only",
                              final_status=result["status"], final_version=result["version"])
            report["after_total"] = checked(analyst.get("/api/admin/requests"))["total"]
            print(json.dumps(report, ensure_ascii=True))
        finally:
            for client in clients.values():
                client.post("/api/auth/logout")


if __name__ == "__main__":
    main()
