from html import escape


def page(title, heading, description, fields, button_text, error=""):
    error_html = (
        f'<div class="error">{escape(error)}</div>'
        if error else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} | Nexus Requests</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    min-height: 100vh;
    background-color: #071d39;
    background-image: linear-gradient(125deg,rgba(2,12,32,.43),rgba(2,19,46,.38)), url('/static/nexus-background.webp');
    background-position: center;
    background-size: cover;
    background-attachment: fixed;
    background-repeat: no-repeat;
    color: #f2f4f8;
    font-family: system-ui, sans-serif;
    display: grid;
    place-items: center;
}}
.panel {{
    width: min(420px, 92vw);
    background: rgba(7,30,64,.78);
    border: 1px solid rgba(100,205,255,.315);
    border-radius: 16px;
    padding: 32px;
}}
h1 {{ margin: 0 0 8px; font-size: 26px; }}
p {{ color: #b4cbe3; line-height: 1.5; text-align: center; }}
label {{ display: block; margin-top: 18px; }}
input {{
    width: 100%;
    margin-top: 7px;
    padding: 12px;
    border-radius: 8px;
    border: 1px solid #414a5c;
    background: #111722;
    color: white;
}}
button {{
    width: 100%;
    margin-top: 25px;
    padding: 13px;
    border: 1px solid rgba(100,205,255,.5);
    border-radius: 8px;
    background: rgba(20,126,191,.22);
    color: white;
    font-weight: 600;
    cursor: pointer;
}}
.error {{
    padding: 12px;
    background: #54272e;
    border-radius: 8px;
    color: #ffced3;
}}
</style>
</head>
<body>
<main class="panel">
<img src="/static/nexus-requests-logo-v3.png" alt="Nexus Requests" style="display:block;width:233px;max-width:100%;height:auto;margin:0 auto 16px">
<p>{escape(description)}</p>
{error_html}
<form method="post">
{fields}
<button type="submit">{escape(button_text)}</button>
</form>
</main>
</body>
</html>"""


USERNAME = '''
<label>Username
<input name="username" autocomplete="username"
       minlength="3" maxlength="32" required>
</label>
'''

PASSWORD = '''
<label>Password
<input type="password" name="password"
       autocomplete="current-password" required>
</label>
'''

NEW_PASSWORD = '''
<label>Password
<input type="password" name="password"
       autocomplete="new-password" minlength="8" maxlength="128" required>
</label>
<label>Confirm password
<input type="password" name="confirm_password"
       autocomplete="new-password" minlength="8" maxlength="128" required>
</label>
'''


def setup_page(error=""):
    return page(
        "Setup",
        "Welcome to Nexus Requests",
        "Create your administrator account to get started.",
        """<label>Setup Token
<input name="setup_token" type="password"
       autocomplete="off" required>
</label>
""" + USERNAME + NEW_PASSWORD,
        "Create Administrator",
        error,
    )


def login_page(error=""):
    return page(
        "Login",
        "Nexus Requests",
        "Sign in to your dashboard.",
        USERNAME + PASSWORD,
        "Sign In",
        error,
    )
