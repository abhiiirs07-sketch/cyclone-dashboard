"""
Earth Engine authentication.

The backend authenticates as a *service account*, not a personal Google
login — the standard pattern for a server that needs to call Earth Engine
on its own, without a human clicking "sign in" each time (this is also
what GEE's own docs recommend for App Engine / Cloud Run deployments).

Required environment variables (see .env.example / README.md):
  EE_SERVICE_ACCOUNT   service account email
  EE_PRIVATE_KEY_FILE  path to that service account's JSON key file
  EE_PROJECT           your GCP project ID (registered for Earth Engine)

Initialization is lazy and cached: importing this module never talks to
Google, so the FastAPI app can start and report a clear "not configured"
status instead of crashing when credentials aren't set up yet.
"""

import os

import ee

_initialized = False


class EENotConfiguredError(RuntimeError):
    pass


def ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return

    sa_email = os.environ.get("EE_SERVICE_ACCOUNT")
    key_file = os.environ.get("EE_PRIVATE_KEY_FILE")
    key_data = os.environ.get("EE_PRIVATE_KEY_DATA")
    project = os.environ.get("EE_PROJECT")

    # If service account credentials are provided, use them.
    if sa_email and (key_file or key_data):
        try:
            if key_file:
                if not os.path.isfile(key_file):
                    raise EENotConfiguredError(
                        f"EE_PRIVATE_KEY_FILE is set to '{key_file}' but that file "
                        "doesn't exist. Double-check the path in .env."
                    )
                credentials = ee.ServiceAccountCredentials(sa_email, key_file)
            else:
                # Load JSON private key directly from env variable
                import json
                try:
                    key_dict = json.loads(key_data)
                except Exception as e:
                    raise EENotConfiguredError(
                        f"EE_PRIVATE_KEY_DATA is not a valid JSON string: {e}"
                    ) from e
                
                if "private_key" in key_dict and isinstance(key_dict["private_key"], str):
                    key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
                
                # ee.ServiceAccountCredentials expects key_data parameter to be a JSON string or dict (if supported by google-auth)
                # In google-auth, ServiceAccountCredentials can accept key_data as JSON string.
                credentials = ee.ServiceAccountCredentials(sa_email, key_data=json.dumps(key_dict))
            
            ee.Initialize(credentials, project=project)
            _initialized = True
            return
        except Exception as e:
            raise EENotConfiguredError(
                f"Failed to initialize Earth Engine with service account: {e}"
            ) from e

    # Try OAuth refresh token if provided
    refresh_token = os.environ.get("EE_REFRESH_TOKEN")
    if refresh_token:
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id="517222506229-vsmmajv00ul0bs7p89v5m89qs8eb9359.apps.googleusercontent.com",
                client_secret="RUP0RZ6e0pPhDzsqIJ7KlNd1",
                scopes=[
                    "https://www.googleapis.com/auth/earthengine",
                    "https://www.googleapis.com/auth/cloud-platform",
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/devstorage.full_control",
                ],
            )
            creds.refresh(Request())
            ee.Initialize(credentials=creds, project=project)
            _initialized = True
            return
        except Exception as e:
            raise EENotConfiguredError(
                f"Failed to initialize Earth Engine with refresh token: {e}"
            ) from e

    # Otherwise, fall back to user credentials (OAuth)
    try:
        ee.Initialize(project=project)
        _initialized = True
    except Exception as e:
        raise EENotConfiguredError(
            "Earth Engine isn't configured yet. Either set EE_SERVICE_ACCOUNT and "
            "EE_PRIVATE_KEY_FILE / EE_PRIVATE_KEY_DATA in .env for service account access, or run "
            "`ee.Authenticate()` in your terminal.\n"
            f"Error details: {e}"
        ) from e
