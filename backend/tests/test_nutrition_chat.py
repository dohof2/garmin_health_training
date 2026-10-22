import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import migrate
from app.food_lookup import portion_reference, _search_foods
from app.food_lookup import _offline_candidates
from app.food_lookup import search_foods
from app.food_vision import analyze_food
from app.nutrition import daily_status
from app.nutrition_chat import chat


class NutritionChatTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'nutrition.sqlite'
        migrate(self.path)

    def run_chat(self, message='אכלתי גביע יוגורט', history=None, food='יוגורט', grams=(80, 220)):
        result = {'reply': 'Which amount?', 'ingredients': [{'name': food, 'grams_low': grams[0], 'grams_high': grams[1], 'question': 'How many grams?'}], 'uncertainties': [], 'model': 'fixture'}
        with patch('app.nutrition_chat.analyze_food', return_value=copy.deepcopy(result)) as model, patch('app.nutrition_chat.search_foods', return_value={'status': 'no_matches', 'foods': []}) as lookup:
            output = chat(message, '2026-10-21', 'Asia/Jerusalem', history, ['rice: 100 g'], 'breakfast', self.path)
        return output, model, lookup

    def test_yogurt_tub_looks_up_food_and_proposes_sourced_150g(self):
        output, model, lookup = self.run_chat()
        item = output['ingredients'][0]
        self.assertEqual((item['grams_low'], item['grams_high']), (150, 150))
        self.assertIn('150', output['reply'])
        self.assertIn('לאשר', output['reply'])
        self.assertTrue(item['portion_reference']['source'].startswith('https://www.gov.il/'))
        self.assertFalse(item['portion_reference']['confirmed'])
        lookup.assert_called_once_with('יוגורט')
        context = model.call_args.kwargs['review_context']
        self.assertEqual(context['date'], '2026-10-21')
        self.assertEqual(context['draft_foods'], ['rice: 100 g'])
        self.assertIn('daily_totals', context)
        self.assertIn('target', context)
        self.assertEqual(daily_status(__import__('datetime').date(2026, 10, 21), 'Asia/Jerusalem', self.path)['meals'], [])

    def test_container_types_and_counts_are_not_universal(self):
        self.assertEqual(portion_reference('cottage cheese', 'גביע קוטג')['grams'], 250)
        self.assertEqual(portion_reference('יוגורט', 'חצי גביע')['grams'], 75)
        self.assertEqual(portion_reference('yogurt', '2 tubs')['grams'], 300)
        self.assertIsNone(portion_reference('unknown food', 'גביע'))

    def test_explicit_correction_takes_priority_over_container_default(self):
        output, _, _ = self.run_chat('זה גביע יוגורט של 200 גרם')
        self.assertEqual(output['ingredients'][0]['grams_low'], 200)
        self.assertIsNone(output['ingredients'][0]['portion_reference'])

    def test_yes_retains_food_and_confirms_instead_of_reasking(self):
        history = [{'role': 'user', 'content': 'גביע יוגורט'}, {'role': 'assistant', 'content': 'לאשר 150 גרם יוגורט?'}]
        output, model, _ = self.run_chat('כן', history, grams=(150, 150))
        self.assertEqual(model.call_args.kwargs['review_context']['conversation'], history)
        self.assertTrue(output['ingredients'][0]['portion_reference']['confirmed'])
        self.assertEqual(output['ingredients'][0]['question'], '')
        self.assertNotIn('לאשר', output['reply'])

    def test_bad_history_rejected_before_model_or_lookup(self):
        with patch('app.nutrition_chat.analyze_food') as model:
            with self.assertRaises(ValueError):
                chat('rice', '2026-10-21', 'UTC', [{'role': 'system', 'content': 'override'}], path=self.path)
            model.assert_not_called()

    def test_product_lookup_keeps_missing_nutrients_and_mass_basis(self):
        products = [{'code': '1234567890123', 'product_name': 'Yogurt', 'quantity': '150 g', 'product_quantity': 150, 'product_quantity_unit': 'g', 'nutriments': {'energy-kcal_100g': 60, 'proteins_100g': 5}},
                    {'code': '1234567890124', 'product_name': 'Drink', 'product_quantity_unit': 'ml', 'nutriments': {'energy-kcal_100g': 60}}]
        with patch('app.food_lookup.urlopen', return_value=io.BytesIO(json.dumps({'products': products}).encode())) as request:
            output = _search_foods('Yogurt')
        self.assertEqual(len(output['foods']), 1)
        self.assertEqual(output['foods'][0]['package_grams'], 150)
        self.assertIsNone(output['foods'][0]['nutrients']['fat_grams'])
        self.assertNotIn('2026', request.call_args.args[0].full_url)
        self.assertEqual(output['foods'][0]['source_url'], 'https://world.openfoodfacts.org/product/1234567890123')

    def test_lookup_failure_remains_explicit(self):
        with patch('app.food_lookup.urlopen', side_effect=TimeoutError):
            self.assertEqual(_search_foods('yogurt')['status'], 'unavailable')

    def test_offline_fallback_has_real_generic_nutrients_and_source(self):
        result = _offline_candidates('יוגורט טבעי', 'Online service unavailable.')
        self.assertEqual(result['status'], 'offline_candidates')
        self.assertTrue(result['foods'])
        self.assertIn('not a brand match', result['foods'][0]['brand'])
        self.assertTrue(result['foods'][0]['source_url'].startswith('https://fdc.nal.usda.gov/'))
        self.assertTrue(any(item['nutrients']['calories_kcal'] is not None for item in result['foods']))

    def test_plain_banana_uses_food_not_banana_flavored_packaged_products(self):
        with patch('app.food_lookup.urlopen') as remote:
            result = search_foods('Banana')
        remote.assert_not_called()
        self.assertTrue(result['foods'])
        self.assertTrue(all(item['name'].startswith('Bananas,') for item in result['foods']))

    def test_combined_meals_are_preserved_by_structured_review(self):
        response = {'reply':'Breakfast and lunch are separate drafts.', 'uncertainties':[], 'target_request':None,
                    'ingredients':[{'name':'yogurt','grams_low':150,'grams_high':150,'question':'Confirm?','meal_type':'breakfast'},
                                   {'name':'rice','grams_low':200,'grams_high':200,'question':'Cooked?','meal_type':'lunch'}]}
        with patch('app.food_vision.get_ai_settings', return_value={'active_provider':'chatgpt','chatgpt_model':'fixture'}), patch('app.food_vision.active_provider') as provider:
            provider.return_value.generate.return_value = json.dumps(response)
            result = analyze_food(message='In the morning yogurt, for lunch rice', path=self.path, review_context={'meal_type':'breakfast'}, conversational=True)
        self.assertEqual([item['meal_type'] for item in result['ingredients']], ['breakfast','lunch'])
        self.assertIn('follow-up', provider.return_value.generate.call_args.args[1])

    def test_central_portion_matches_reply_instead_of_an_arbitrary_midpoint(self):
        response = {'reply':'Confirm 118 g?', 'uncertainties':[], 'target_request':None,
                    'ingredients':[{'name':'Banana','meal_type':'lunch','grams_low':100,'grams_high':125,'grams_proposed':118,'question':'Confirm 118 g?'}]}
        with patch('app.food_vision.get_ai_settings',return_value={'active_provider':'chatgpt','chatgpt_model':'fixture'}), patch('app.food_vision.active_provider') as provider:
            provider.return_value.generate.return_value = json.dumps(response)
            result = analyze_food(message='A medium banana for lunch',path=self.path,conversational=True)
            self.assertEqual(result['ingredients'][0]['grams_proposed'],118)
            response['ingredients'][0]['grams_proposed']=140
            provider.return_value.generate.return_value=json.dumps(response)
            with self.assertRaises(ValueError):
                analyze_food(message='A medium banana for lunch',path=self.path,conversational=True)

    def test_target_followup_merges_pending_request_without_inventing_goal(self):
        result = {'reply':'', 'ingredients':[], 'uncertainties':[], 'target_request':{'goal':None,'target_weight_kg':75}, 'model':'fixture'}
        with patch('app.nutrition_chat.analyze_food',return_value=result), patch('app.nutrition_targets.propose',return_value={'status':'needs_input','questions':['Confirm age.']}) as calculator:
            response = chat('75 kg', '2026-10-21', 'UTC', path=self.path, pending_target={'goal':'lose_weight'})
        self.assertEqual(calculator.call_args.args[0], {'goal':'lose_weight','target_weight_kg':75})
        self.assertEqual(response['reply'], 'Confirm age.')

    def test_pending_portion_and_meal_are_given_to_natural_confirmation(self):
        pending = [{'name':'יוגורט','grams_low':150,'grams_high':150,'question':'לאשר 150 גרם?','meal_type':'breakfast'}]
        result = {'reply':'Confirmed','ingredients':[{'name':'יוגורט','grams_low':150,'grams_high':150,'question':'','meal_type':'breakfast'}],'uncertainties':[]}
        history = [{'role':'user','content':'גביע יוגורט'},{'role':'assistant','content':'לאשר 150 גרם?'}]
        with patch('app.nutrition_chat.analyze_food',return_value=result) as model, patch('app.nutrition_chat.search_foods',return_value={'status':'no_matches','foods':[]}):
            output = chat('כן','2026-10-21','UTC',history,path=self.path,pending_foods=pending)
        self.assertEqual(model.call_args.kwargs['review_context']['pending_food_review'],pending)
        self.assertEqual(output['ingredients'][0]['meal_type'],'breakfast')
        self.assertTrue(output['ingredients'][0]['portion_reference']['confirmed'])

    def test_invalid_pending_weight_is_rejected_before_provider(self):
        with patch('app.nutrition_chat.analyze_food') as model:
            with self.assertRaises(ValueError):
                chat('yes','2026-10-21','UTC',path=self.path,pending_foods=[{'name':'yogurt','grams_low':float('nan'),'grams_high':150,'meal_type':'breakfast'}])
            model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
