"""Headless Kite Connect login using Zerodha's username/password + TOTP.

Kite Connect's official generate_session() flow requires a `request_token`
obtained by an interactive browser login. This module drives that login
through Zerodha's own web login endpoints (the same ones kite.zerodha.com
uses) so it can run unattended in a scheduled job.

This depends on Zerodha's undocumented internal login API and is
inherently fragile: if Zerodha changes their login flow, adds a captcha,
or rate-limits automated logins, this will start failing and needs to be
updated. It is a deliberate tradeoff for zero-touch daily automation; see
docs/SETUP.md for the manual-token fallback if this breaks.
"""
from urllib.parse import urlparse, parse_qs

import pyotp
import requests
from kiteconnect import KiteConnect

LOGIN_URL = 'https://kite.zerodha.com/api/login'
TWOFA_URL = 'https://kite.zerodha.com/api/twofa'


class KiteLoginError(RuntimeError):
    pass


class KiteTOTPLogin:
    def __init__(self, api_key, api_secret, user_id, password, totp_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.user_id = user_id
        self.password = password
        self.totp_secret = totp_secret
        self.session = requests.Session()

    def _request_token(self):
        resp = self.session.post(LOGIN_URL, data={
            'user_id': self.user_id,
            'password': self.password,
        }, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get('status') != 'success':
            raise KiteLoginError('Zerodha login (step 1) failed: %s' % payload.get('message'))
        request_id = payload['data']['request_id']

        totp_code = pyotp.TOTP(self.totp_secret).now()
        resp = self.session.post(TWOFA_URL, data={
            'user_id': self.user_id,
            'request_id': request_id,
            'twofa_value': totp_code,
            'twofa_type': 'totp',
        }, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get('status') != 'success':
            raise KiteLoginError('Zerodha login (TOTP step) failed: %s' % payload.get('message'))

        kite = KiteConnect(api_key=self.api_key)
        login_redirect = self.session.get(kite.login_url(), timeout=30)

        request_token = None
        for resp in list(login_redirect.history) + [login_redirect]:
            qs = parse_qs(urlparse(resp.url).query)
            if 'request_token' in qs:
                request_token = qs['request_token'][0]
                break

        if not request_token:
            raise KiteLoginError(
                'Could not extract request_token from Zerodha login redirect. '
                'The login flow may have changed, or 2FA/TOTP failed silently.'
            )
        return request_token

    def get_access_token(self):
        request_token = self._request_token()
        kite = KiteConnect(api_key=self.api_key)
        session_data = kite.generate_session(request_token, api_secret=self.api_secret)
        return session_data['access_token']
