"""Offline security and protocol checks; no real accounts or health data."""
import base64
import hashlib
import json
import logging
import ssl
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from app import chatgpt_auth as auth
from app.ai_chat import _chatgpt_stream
from app.ai_providers import ChatGPTProvider


class ChatGPTAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'test.sqlite3'
        auth._PENDING.clear()

    def begin(self, account=None):
        return {k: v[0] for k, v in parse_qs(urlparse(auth.start(self.path, account)['authorization_url']).query).items()}

    def finish(self, args, **claims_override):
        claims = {'iss': auth.ISSUER, 'aud': 'issued-client', 'sub': 'user-one',
                  'nonce': args['nonce'], 'exp': int(time.time()) + 3600,
                  'email': 'tester@example.invalid', **claims_override}
        tokens = {'access_token': 'access-secret', 'refresh_token': 'refresh-secret',
                  'token_type': 'Bearer', 'scope': auth.SCOPES, 'expires_in': 3600,
                  'id_token': jwt.encode(claims, self.key, algorithm='RS256')}
        def respond(url, form=None, token=None):
            if form:
                self.assertEqual(form['client_id'], 'issued-client')
                self.assertEqual(form['redirect_uri'], auth.CALLBACK)
                return tokens
            return {'issuer': auth.ISSUER, 'jwks_uri': auth.ISSUER + '/jwks',
                    'revocation_endpoint': auth.ISSUER + '/revoke'}
        with patch.object(auth, '_json', side_effect=respond), patch.object(auth.jwt, 'PyJWKClient') as jwks:
            jwks.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())
            return auth.finish({'state': args['state'], 'client_id': 'issued-client', 'code': 'one-use-code'})

    def test_loopback_pkce_and_stable_host(self):
        first = self.begin()
        pending = auth._PENDING[first['state']]
        expected = base64.urlsafe_b64encode(hashlib.sha256(pending['verifier'].encode()).digest()).decode().rstrip('=')
        self.assertEqual(first['code_challenge'], expected)
        self.assertEqual(first['client_id'], 'dynamic_agent_client')
        self.assertEqual(first['redirect_uri'], auth.CALLBACK)
        self.assertIn('chatgpt.tokens.use.direct', first['scope'])
        self.assertNotIn('email', first['scope'].split())
        self.assertNotIn('profile', first['scope'].split())
        second = self.begin()
        self.assertEqual(first['ext_agent_host_id'], second['ext_agent_host_id'])
        self.assertNotEqual(first['state'], second['state'])
        self.assertIn(first['state'], auth._PENDING)

    def test_parallel_browser_handoffs_remain_valid_and_are_bounded(self):
        first = self.begin()
        self.begin()
        self.assertTrue(self.finish(first)['connected'])
        for _ in range(10):
            self.begin()
        self.assertLessEqual(len(auth._PENDING), 8)

    def test_failure_messages_do_not_echo_credentials_or_server_payloads(self):
        from urllib.error import HTTPError
        for error in (ValueError('access-secret'), jwt.InvalidTokenError('refresh-secret'), HTTPError('https://example.invalid?code=secret', 400, 'id-token-secret', {}, None)):
            message = auth.failure_message(error)
            self.assertNotIn('secret', message)
        args = self.begin()
        auth._PENDING[args['state']]['created'] = 0
        with self.assertRaises(auth.SignInError) as failure:
            auth.finish({'state': args['state']})
        self.assertEqual(failure.exception.code, 'expired_state')
        self.assertIn('fresh link for Chrome', auth.failure_message(failure.exception))

    def test_valid_signature_identity_and_private_storage(self):
        args = self.begin()
        status = self.finish(args)
        self.assertTrue(status['connected'])
        self.assertNotIn('access-secret', json.dumps(status))
        self.assertNotIn('refresh-secret', json.dumps(status))
        self.assertNotIn('tester@example.invalid', json.dumps(status))
        account=auth._read(self.path)['accounts']['issued-client']
        self.assertNotIn('email',account)
        self.assertNotIn('id_token',account['tokens'])
        self.assertEqual(auth._file(self.path).stat().st_mode & 0o777, 0o600)
        self.assertEqual(auth.access_token(self.path), 'access-secret')
        with self.assertRaises(ValueError):
            auth.finish({'state': args['state'], 'code': 'replay'})

    def test_invalid_identity_does_not_replace_active_account(self):
        self.finish(self.begin())
        before = auth._file(self.path).read_text()
        for override in ({'nonce': 'wrong'}, {'aud': 'wrong'}, {'iss': 'https://wrong.invalid'}, {'exp': 1}):
            with self.subTest(override=override):
                args = self.begin('issued-client')
                with self.assertRaises((ValueError, jwt.PyJWTError)):
                    self.finish(args, **override)
                self.assertEqual(auth._file(self.path).read_text(), before)
        with self.assertRaises(ValueError):
            self.finish(self.begin('issued-client'), sub='different-user')
        self.assertEqual(auth._file(self.path).read_text(), before)

    def test_denial_expiry_and_missing_client_do_not_exchange_tokens(self):
        for extra in ({'error': 'access_denied'}, {'code': 'code'}, {'client_id': 'dynamic_agent_client', 'code': 'code'}):
            args = self.begin()
            with patch.object(auth, '_json') as network, self.assertRaises(ValueError):
                auth.finish({'state': args['state'], **extra})
            network.assert_not_called()
        args = self.begin()
        auth._PENDING[args['state']]['created'] = time.time() - 601
        with self.assertRaises(ValueError):
            auth.finish({'state': args['state'], 'client_id': 'issued-client', 'code': 'code'})

    def test_refresh_rotates_and_withdrawn_permission_blocks_usage(self):
        self.finish(self.begin())
        data = auth._read(self.path)
        data['accounts']['issued-client']['expires_at'] = 0
        auth._save(data, self.path)
        with patch.object(auth, '_json', return_value={'access_token': 'renewed', 'refresh_token': 'rotated', 'expires_in': 3600}) as network:
            self.assertEqual(auth.access_token(self.path), 'renewed')
        self.assertEqual(network.call_args.args[1]['refresh_token'], 'refresh-secret')
        data = auth._read(self.path)
        self.assertEqual(data['accounts']['issued-client']['tokens']['refresh_token'], 'rotated')
        data['accounts']['issued-client']['expires_at'] = 0
        auth._save(data, self.path)
        with patch.object(auth, '_json', return_value={'access_token': 'blocked', 'refresh_token': 'rotated-again', 'expires_in': 3600, 'scope': 'openid'}):
            with self.assertRaisesRegex(RuntimeError, 'not authorized'):
                auth.access_token(self.path)
        self.assertFalse(auth.status(self.path)['connected'])

    def test_catalog_filters_visibility_and_preserves_account_order(self):
        with patch.object(auth, 'access_token', return_value='fake'), patch.object(auth, '_json', return_value={'models': [
            {'slug': 'first', 'display_name': 'First', 'visibility': 'list'},
            {'slug': 'hidden', 'display_name': 'Hidden', 'visibility': 'hidden'},
            {'slug': 'second', 'display_name': 'Second', 'visibility': 'list'}]}):
            self.assertEqual([m['id'] for m in auth.models(self.path)], ['first', 'second'])

    def test_signout_clears_local_tokens_when_revocation_fails(self):
        self.finish(self.begin())
        with patch.object(auth, '_discovery', side_effect=OSError('offline')):
            result = auth.sign_out(self.path)
        self.assertFalse(result['remote_revocation_confirmed'])
        self.assertFalse(result['connected'])
        self.assertEqual(auth._read(self.path)['accounts']['issued-client']['tokens'], {})
        self.assertEqual(self.begin('issued-client')['client_id'], 'issued-client')

    def test_callback_logging_redacts_query(self):
        record = logging.LogRecord('uvicorn.access', 20, '', 0, '%s %s %s %s %s',
                                   ('127.0.0.1', 'GET', '/auth/callback?code=secret&state=secret', 'HTTP/1.1', 200), None)
        auth._CallbackLogFilter().filter(record)
        self.assertNotIn('secret', record.getMessage())

    def test_oauth_http_and_identity_keys_use_verified_tls(self):
        context = auth._tls_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        with patch.object(auth, 'urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = b'{}'
            auth._json(auth.ISSUER + '/.well-known/openid-configuration')
        self.assertTrue(request.call_args.kwargs['context'].check_hostname)
        args = self.begin()
        with patch.object(auth, '_tls_context', return_value=context) as tls:
            self.finish(args)
        tls.assert_called_once()

    def test_certificate_failure_has_specific_safe_message(self):
        from urllib.error import URLError
        message = auth.failure_message(URLError(ssl.SSLCertVerificationError('secret')))
        self.assertIn('TLS certificate', message)
        self.assertNotIn('secret', message)

    def test_existing_account_profile_is_removed_without_losing_connection(self):
        self.finish(self.begin())
        data=auth._read(self.path)
        account=data['accounts']['issued-client']
        account['email']='old@example.invalid'
        account['tokens']['id_token']='old-identity-token'
        auth._save(data,self.path)
        self.assertTrue(auth.status(self.path)['connected'])
        persisted=json.loads(auth._file(self.path).read_text())['accounts']['issued-client']
        self.assertNotIn('email',persisted)
        self.assertNotIn('id_token',persisted['tokens'])
        self.assertEqual(auth.access_token(self.path),'access-secret')


class ChatGPTStreamTests(unittest.TestCase):
    def test_metadata_only_completion_uses_streamed_items_and_text(self):
        call=SimpleNamespace(type='function_call',call_id='one',name='assess_ride',arguments='{}')
        terminal=SimpleNamespace(type='response.completed',response=SimpleNamespace(output=[],output_text=''))
        outputs=[{'serialized':'{"recorded_benefit":"aerobic_base"}'}]
        with patch('app.chatgpt_auth.models',return_value=[{'id':'account-model'}]),patch('app.chatgpt_auth.access_token',return_value='fake'),patch('app.ai_chat.OpenAI') as client,patch('app.ai_chat._execute_calls',return_value=(outputs,[{'tool':'assess_ride'}])):
            client.return_value.responses.create.side_effect=[iter([SimpleNamespace(type='response.output_item.done',item=call),terminal]),iter([SimpleNamespace(type='response.output_text.delta',delta='Useful endurance work.'),terminal])]
            events=list(_chatgpt_stream('account-model','Was it good?',[], 'UTC',None))
        self.assertIn('Useful endurance work.',''.join(events))

    def test_trainer_clarification_is_not_replaced_with_generic_failure(self):
        terminal=SimpleNamespace(type='response.completed',response=SimpleNamespace(output=[],output_text='What was your goal for that session?'))
        with patch('app.chatgpt_auth.models',return_value=[{'id':'account-model'}]),patch('app.chatgpt_auth.access_token',return_value='fake'),patch('app.ai_chat.OpenAI') as client:
            client.return_value.responses.create.return_value=iter([terminal])
            events=list(_chatgpt_stream('account-model','Was it good?',[], 'UTC',None))
        self.assertIn('What was your goal', ''.join(events))
        self.assertNotIn('could not retrieve', ''.join(events))

    def test_trainer_uses_tool_evidence_and_model_written_answer(self):
        call=SimpleNamespace(type='function_call',call_id='one',name='assess_ride',arguments='{}')
        first=SimpleNamespace(type='response.completed',response=SimpleNamespace(output=[call],output_text=''))
        final=SimpleNamespace(type='response.completed',response=SimpleNamespace(output=[],output_text='Yes—useful endurance work. Keep tomorrow easy.'))
        outputs=[{'serialized':'{"recorded_benefit":"aerobic_base"}'}]
        with patch('app.chatgpt_auth.models',return_value=[{'id':'account-model'}]),patch('app.chatgpt_auth.access_token',return_value='fake'),patch('app.ai_chat.OpenAI') as client,patch('app.ai_chat._execute_calls',return_value=(outputs,[{'tool':'assess_ride'}])),patch('app.ai_chat._deterministic_answer',side_effect=AssertionError('No canned trainer answers')):
            client.return_value.responses.create.side_effect=[iter([first]),iter([final])]
            events=list(_chatgpt_stream('account-model','Was it good?',[], 'UTC',None))
        self.assertIn('useful endurance work',''.join(events))
        self.assertEqual(client.return_value.responses.create.call_count,2)
        self.assertIn('aerobic_base',json.dumps(client.return_value.responses.create.call_args.kwargs['input'],default=str))

    def test_chatgpt_bypasses_legacy_question_shortcuts(self):
        from app.ai_chat import chat_stream
        settings={'active_provider':'chatgpt','chatgpt_model':'account-model'}
        with patch('app.ai_chat.get_ai_settings',return_value=settings),patch('app.ai_chat._chatgpt_stream',return_value=iter(['trainer answer\n'])) as trainer,patch('app.plot_requests.history_request',side_effect=AssertionError('No Qwen routing')):
            result=list(chat_stream('How were my steps this year?'))
        trainer.assert_called_once()
        self.assertEqual(result[-1],'trainer answer\n')

    def test_namespaced_tools_and_required_stream_contract(self):
        terminal = SimpleNamespace(type='response.completed', response=SimpleNamespace(output=[], output_text='Hello'))
        with patch('app.chatgpt_auth.models', return_value=[{'id': 'account-model'}]), patch('app.chatgpt_auth.access_token', return_value='fake'), patch('app.ai_chat.OpenAI') as client:
            client.return_value.responses.create.return_value = iter([terminal])
            events = list(_chatgpt_stream('account-model', 'Hello', [], 'UTC', None))
        args = client.return_value.responses.create.call_args.kwargs
        self.assertTrue(args['stream'])
        self.assertFalse(args['store'])
        self.assertIsInstance(args['input'], list)
        self.assertEqual(args['tools'][0]['type'], 'namespace')
        functions=args['tools'][0]['tools']
        proposal=next(function for function in functions if function['name']=='propose_settings_change')
        self.assertEqual(proposal['parameters']['properties']['target']['enum'],['profile','goals'])
        self.assertNotIn('log_maintenance',{function['name'] for function in functions})
        self.assertNotIn('max_output_tokens', args)
        self.assertNotIn('temperature', args)
        self.assertIn('complete', ''.join(events))

    def test_failed_or_unfinished_stream_never_completes(self):
        for stream in ([], [SimpleNamespace(type='response.failed')], [SimpleNamespace(type='response.incomplete')]):
            with self.subTest(stream=stream), patch('app.chatgpt_auth.models', return_value=[{'id': 'account-model'}]), patch('app.chatgpt_auth.access_token', return_value='fake'), patch('app.ai_chat.OpenAI') as client:
                client.return_value.responses.create.return_value = iter(stream)
                with self.assertRaises(RuntimeError):
                    list(_chatgpt_stream('account-model', 'Hello', [], 'UTC', None))

    def test_missing_model_never_requests_inference(self):
        with patch('app.chatgpt_auth.models', return_value=[]), patch('app.ai_chat.OpenAI') as client:
            with self.assertRaisesRegex(RuntimeError, 'not available'):
                list(_chatgpt_stream('wrong', 'Hello', [], 'UTC', None))
        client.assert_not_called()

    def test_sol_uses_light_reasoning(self):
        terminal = SimpleNamespace(type='response.completed', response=SimpleNamespace(output=[], output_text='Hello'))
        with patch('app.chatgpt_auth.models', return_value=[{'id': 'gpt-6-sol'}]), patch('app.chatgpt_auth.access_token', return_value='fake'), patch('app.ai_chat.OpenAI') as client:
            client.return_value.responses.create.return_value = iter([terminal])
            list(_chatgpt_stream('gpt-6-sol', 'Hello', [], 'UTC', None))
        self.assertEqual(client.return_value.responses.create.call_args.kwargs['reasoning'], {'effort': 'low'})

    def test_general_provider_requires_terminal_success(self):
        with patch('app.chatgpt_auth.access_token', return_value='fake'), patch('app.ai_providers.OpenAI') as client:
            client.return_value.responses.create.return_value = iter([SimpleNamespace(type='response.output_text.delta', delta='partial')])
            with self.assertRaisesRegex(RuntimeError, 'before completion'):
                ChatGPTProvider('account-model').generate('Hello', 'Be concise')
