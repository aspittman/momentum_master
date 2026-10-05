import unittest
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
from requests.exceptions import Timeout
from trading_ownership.guard import OwnershipError
import trader

class StopReconciliationTests(unittest.TestCase):
    def attempt(self,effects):
        client=Mock();client.submit_order.side_effect=effects
        with patch.object(trader,'get_trading_client',return_value=client), \
             patch.object(trader.bot_state,'protective_stop',return_value={}), \
             patch.object(trader.bot_state,'set_protective_stop') as save, \
             patch.object(trader.time,'sleep') as sleep:
            try:result=trader.ensure_protective_stop('MU',.2,100)
            except Exception as exc:result=exc
        return result,client,save,sleep

    def test_fill_visibility_lag_retries_full_guard_then_protects(self):
        result,client,save,sleep=self.attempt([
            OwnershipError('Position ownership no longer reconciles: MU'),N(id='stop')])
        self.assertIs(result,True);self.assertEqual(client.submit_order.call_count,2)
        self.assertIs(client.submit_order.call_args_list[0].args[0],client.submit_order.call_args_list[1].args[0])
        save.assert_called_once_with('MU','stop',100);sleep.assert_called_once_with(1)

    def test_persistent_mismatch_remains_blocked(self):
        result,client,save,sleep=self.attempt([OwnershipError('Position ownership no longer reconciles: MU')]*5)
        self.assertIsInstance(result,OwnershipError)
        self.assertEqual(client.submit_order.call_count,5);self.assertEqual(sleep.call_count,4);save.assert_not_called()

    def test_ambiguous_post_and_foreign_ownership_never_retried(self):
        for exc in (Timeout('unknown submission'),OwnershipError('Instrument position belongs to another or unknown trader'),
                    OwnershipError('Position ownership no longer reconciles: NVDA')):
            result,client,save,sleep=self.attempt([exc])
            self.assertIs(result,exc);self.assertEqual(client.submit_order.call_count,1)
            save.assert_not_called();sleep.assert_not_called()
