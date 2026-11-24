#!/usr/bin/env python3
"""Check the applicant flow of the Loan API end to end, documents included.

A self-service applicant uploads random documents straight to storage with presigned policies, submits an application
that names them, attaches one more document afterwards and reads the application back. Bad requests are tried too:
no token, wrong content type, too large, missing ID sides, someone else's document, a document that was never uploaded.

Environment:
  TOKEN        access token of an applicant (customers realm), required
  API_URL      default http://127.0.0.1:8000
  UPLOAD_BASE  origin to post uploads to instead of the one in the presigned URL, for example http://127.0.0.1:19000
               when storage is reached through a port-forward (the policy signature does not cover the host)
Standard library only. Exit status 1 if any check fails. The token and the personal data are never printed.

Local and lab use only. Not shipped: the root .dockerignore excludes scripts/ from every image.
"""

import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
UPLOAD_BASE = os.environ.get("UPLOAD_BASE", "").rstrip("/")
TOKEN = os.environ["TOKEN"]
MAX_BYTES = 10 * 1024 * 1024
results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail else ""))
    return ok


def call(method: str, path: str, body=None, token: str | None = TOKEN):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw.decode(errors="replace")[:200]


def presign(slot: int, content_type: str):
    return call("POST", "/api/v1/presigned-url", {"document_type": slot, "content_type": content_type})


def upload(policy: dict, content: bytes, content_type: str) -> int:
    """POST a multipart form to storage: the policy fields first, the file last (S3 requires that order)."""
    boundary = "----flow" + secrets.token_hex(8)
    parts = []
    for name, value in policy["fields"].items():
        if name == "Content-Type":
            value = content_type  # the form says what the file claims to be; the policy pins what is allowed
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="random.bin"\r\n'
                 f"Content-Type: {content_type}\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    url = policy["upload_url"]
    if UPLOAD_BASE:
        parsed = urllib.parse.urlsplit(url)
        url = UPLOAD_BASE + parsed.path
    request = urllib.request.Request(url, data=b"".join(parts), method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def random_document(size: int = 4096) -> bytes:
    return secrets.token_bytes(size)


def main() -> int:
    print(f"API {API}")

    # 1. No identity, no entry
    status, _ = call("GET", "/api/v1/me/applications", token=None)
    check("no token is refused", status == 401, f"status {status}")
    status, _ = call("GET", "/api/v1/me/applications", token="not-a-token")
    check("a garbage token is refused", status == 401, f"status {status}")

    # 2. Upload policies
    status, _ = presign(99, "application/pdf")
    check("an unknown document type is refused", status == 400, f"status {status}")
    status, _ = presign(2, "text/plain")
    check("a content type that is not allowed is refused", status == 422, f"status {status}")
    policies = {}
    for slot, content_type in ((2, "image/jpeg"), (15, "image/png"), (3, "application/pdf")):
        status, body = presign(slot, content_type)
        ok = status == 200 and isinstance(body, dict) and {"upload_url", "fields", "document_id", "max_bytes"} <= set(body)
        check(f"policy for slot {slot} ({content_type})", ok, f"status {status}")
        if not ok:
            return finish()
        policies[slot] = (body, content_type)
    check("the policy states the size limit", all(p["max_bytes"] == MAX_BYTES for p, _ in policies.values()))

    # 3. Uploads, good and bad
    for slot, (policy, content_type) in policies.items():
        status = upload(policy, random_document(), content_type)
        check(f"upload of a random document to slot {slot}", status in (200, 201, 204), f"status {status}")
    policy, _ = policies[2]
    status = upload(policy, random_document(), "application/pdf")
    check("a file whose type differs from the policy is refused", status in (400, 403), f"status {status}")
    status, body = presign(21, "application/pdf")
    status = upload(body, random_document(MAX_BYTES + 1024), "application/pdf")
    check("a file over the size limit is refused", status in (400, 403, 413), f"status {status}")

    ids = {f"document_id_{slot}": policy["document_id"] for slot, (policy, _) in policies.items()}
    owner = ids["document_id_2"].split("/")[0]

    application = {
        "birth_date": "1990-05-15",
        "amt_income_total": 180000000,
        "amt_credit": 40000000,
        "name_income_type": "Working",
        "name_education_type": "Higher education",
        "name_family_status": "Married",
        "name_housing_type": "House / apartment",
        "bureau_consent": True,
        "applicant": {
            "full_name": "Test Applicant " + secrets.token_hex(2),
            "citizen_id": "0" + "".join(secrets.choice("0123456789") for _ in range(11)),
            "phone": "09" + "".join(secrets.choice("0123456789") for _ in range(8)),
        },
    }

    # 4. Submissions that must fail
    status, body = call("POST", "/api/v1/applications", {**application})
    check("self-service without documents is refused", status == 422, f"status {status}")
    status, body = call("POST", "/api/v1/applications", {**application, "document_ids": {"document_id_2": ids["document_id_2"]}})
    check("only one side of the ID card is refused", status == 422, f"status {status}")
    stranger = "0" * 24 + "/identity/doc_" + "a" * 32 + ".jpg"
    status, body = call("POST", "/api/v1/applications", {**application, "document_ids": {**ids, "document_id_2": stranger}})
    check("a document that belongs to someone else is refused", status == 403, f"status {status}")
    never_uploaded = f"{owner}/identity/doc_{'b' * 32}.jpg"
    status, body = call("POST", "/api/v1/applications", {**application, "document_ids": {**ids, "document_id_15": never_uploaded}})
    check("a document that was never uploaded is refused", status == 422, f"status {status}")
    status, body = call("POST", "/api/v1/applications", {**application, "document_ids": {**ids, "document_id_3": "../../etc/passwd"}})
    check("a document id that is not a storage key is refused", status in (403, 422), f"status {status}")

    # 5. The real submission
    status, body = call("POST", "/api/v1/applications", {**application, "document_ids": ids})
    if not check("submission with random documents", status == 201 and isinstance(body, dict) and "id" in body, f"status {status}"):
        return finish()
    app_id = body["id"]
    print(f"      application id {app_id}")

    # 6. One more document afterwards
    status, policy = presign(5, "application/pdf")
    check("policy for a bank statement", status == 200, f"status {status}")
    if status == 200:
        check("upload of the bank statement", upload(policy, random_document(), "application/pdf") in (200, 201, 204))
        status, body = call("POST", f"/api/v1/applications/{app_id}/documents", {"slot": 5, "document_id": policy["document_id"]})
        check("attach the bank statement to the application", status in (200, 201, 204), f"status {status}")
        status, body = call("POST", f"/api/v1/applications/{app_id}/documents", {"slot": 6, "document_id": stranger})
        check("attach a document that belongs to someone else is refused", status in (403, 422), f"status {status}")
        status, body = call("POST", f"/api/v1/applications/{app_id}/documents", {"slot": 1, "document_id": policy["document_id"]})
        check("attach to a slot below 2 is refused", status == 422, f"status {status}")

    # 7. Read back
    status, body = call("GET", f"/api/v1/applications/{app_id}")
    check("read the application back", status == 200 and isinstance(body, dict) and body.get("id") == app_id, f"status {status}")
    if status == 200 and isinstance(body, dict):
        text = json.dumps(body)
        check("the response does not carry the citizen id or phone", application["applicant"]["citizen_id"] not in text
              and application["applicant"]["phone"] not in text)
    status, body = call("GET", f"/api/v1/applications/{app_id}/status")
    check("status endpoint answers", status == 200, f"status {status}")
    status, body = call("GET", "/api/v1/me/applications")
    listed = status == 200 and app_id in json.dumps(body)
    check("the application is in my applications", listed, f"status {status}")
    status, _ = call("GET", "/api/v1/applications/00000000-0000-4000-8000-000000000000")
    check("an application that is not mine looks like it does not exist", status in (403, 404), f"status {status}")
    return finish(app_id)


def finish(app_id: str | None = None) -> int:
    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed")
    if app_id:
        print(f"application {app_id}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
