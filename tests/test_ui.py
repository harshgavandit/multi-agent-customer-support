import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from errors import RateLimitExceeded, RateLimitUnavailable, ModelUnavailable
from pipeline import info_gathering, compaction
from session import session_store as store
from test_workflows import ticket


class StreamlitUITests(unittest.TestCase):
    def setUp(self):
        for context in [patch('config.configuration_problems', return_value=[]),
                        patch('pipeline.graph.check_customer_turn'),
                        patch.object(info_gathering, 'complete_json', return_value={'info_complete':True}),
                        patch.object(compaction, 'complete_json', return_value=ticket())]:
            context.start()
            self.addCleanup(context.stop)
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'), default_timeout=15).run()
        self.assertEqual(len(self.app.exception), 0)

    def button(self, label):
        return next(button for button in self.app.button if button.label == label)

    def test_refund_approve_and_resume_through_rendered_views(self):
        self.app.chat_input[0].set_value('Refund 2200 rupees for ORD-1006').run()
        self.assertEqual(len(self.app.exception), 0)
        sid = self.app.session_state['active_session_id']
        record = next(r for r in store.list_pending_approvals() if r['session_id'] == sid)
        self.app.sidebar.radio[0].set_value('Approver Queue').run()
        self.assertEqual(len(self.app.exception), 0)
        next(b for b in self.app.button if b.key == 'approve_' + record['approval_id']).click().run()
        self.assertEqual(store.get_pending_approval(record['approval_id'])['status'], 'approved')
        self.app.sidebar.radio[0].set_value('Customer Chat').run()
        self.assertTrue(any('been approved' in str(markdown.value) for markdown in self.app.markdown))
        self.button('New Session').click().run()
        self.assertNotEqual(self.app.session_state['active_session_id'], sid)
        self.assertEqual(len(self.app.chat_message), 0)
        self.app.sidebar.text_input[0].set_value(sid)
        self.button('Resume').click().run()
        self.assertEqual(self.app.session_state['active_session_id'], sid)
        self.assertTrue(any('been approved' in str(markdown.value) for markdown in self.app.markdown))
        self.assertEqual(len(self.app.exception), 0)

    def test_deny_button_delivers_outcome(self):
        self.app.chat_input[0].set_value('Refund 2200 rupees for ORD-1006').run()
        sid = self.app.session_state['active_session_id']
        record = next(r for r in store.list_pending_approvals() if r['session_id'] == sid)
        self.app.sidebar.radio[0].set_value('Approver Queue').run()
        next(b for b in self.app.button if b.key == 'deny_' + record['approval_id']).click().run()
        self.app.sidebar.radio[0].set_value('Customer Chat').run()
        self.assertTrue(any('unable to approve' in str(markdown.value) for markdown in self.app.markdown))
        self.assertEqual(len(self.app.exception), 0)

    def test_service_errors_render_without_crashing_or_persisting_message(self):
        sid = self.app.session_state['active_session_id']
        for error in (RateLimitExceeded(8), RateLimitUnavailable(), ModelUnavailable('Model unavailable')):
            with patch('pipeline.graph.check_customer_turn', side_effect=error):
                self.app.chat_input[0].set_value('Help').run()
            self.assertEqual(len(self.app.exception), 0)
            self.assertTrue(any(str(error) in e.value for e in self.app.error))
            self.assertEqual(store.get_session(sid)['conversation_history'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
