import json
import os
import uuid
import httpx

API_URL = "http://localhost:8000"


def setup():
    print("Preparing load test credentials...")
    client = httpx.Client(base_url=API_URL, timeout=15.0)

    # 1. Login as admin
    admin_login = client.post(
        "/auth/login",
        json={"email": "admin@classvault.edu", "password": "AdminPassword123!"},
    )
    if admin_login.status_code != 200:
        raise RuntimeError(f"Admin login failed: {admin_login.text}")
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Get available courses
    courses_res = client.get("/courses", headers=admin_headers)
    courses = courses_res.json()
    if not courses:
        raise RuntimeError("No courses found for load testing.")
    course_ids = [c["id"] for c in courses]
    print(f"Found {len(course_ids)} courses for load testing.")

    # 3. Create or login 5 student accounts and join the courses
    tokens = [admin_token]
    for i in range(5):
        s_email = f"loaduser_{i}@classvault.edu"
        s_pass = "LoadPass123!"
        # Try register
        reg = client.post(
            "/auth/register",
            json={"name": f"Load Student {i}", "email": s_email, "password": s_pass, "role": "student"},
        )
        if reg.status_code == 201:
            tok = reg.json().get("access_token")
        else:
            # Login
            log = client.post("/auth/login", json={"email": s_email, "password": s_pass})
            tok = log.json().get("access_token") if log.status_code == 200 else None

        if tok:
            tokens.append(tok)
            # Auto-approve enrollment into the first course
            first_course = courses[0]
            if first_course.get("join_code"):
                join_res = client.post(
                    "/courses/join",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"code": first_course["join_code"]},
                )
                if join_res.status_code == 201:
                    enrollment_id = join_res.json().get("id")
                    # Admin approves
                    client.post(
                        f"/enrollments/{enrollment_id}/review",
                        headers=admin_headers,
                        json={"status": "approved"},
                    )

    print(f"Prepared {len(tokens)} valid auth tokens.")
    out_dir = os.path.join(os.path.dirname(__file__))
    data = {
        "tokens": tokens,
        "course_ids": course_ids,
    }
    with open(os.path.join(out_dir, "test_context.json"), "w") as f:
        json.dump(data, f, indent=2)
    print("Saved load test context to test_context.json")


if __name__ == "__main__":
    setup()
