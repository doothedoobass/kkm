from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import (
    CognitiveMetric,
    Enrollment,
    HealthWalletTransaction,
    MedicalReport,
    NeuroProfile,
    NeurolearnCourse,
    Notification,
    UserFeatureHint,
    WellnessProtocol,
)
from .views import generate_profile_insight


class UserSpecificDashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='uniqueuser',
            email='unique@example.com',
            password='secret123',
        )
        self.profile = NeuroProfile.objects.create(
            user=self.user,
            full_name='Unique User',
            pathway='Research & Innovation',
            cognitive_goal='Memory & Concentration',
            data_processing_consent=True,
            web3_wallet='0xabc123',
        )
        self.course = NeurolearnCourse.objects.create(
            title='Neurolearning Pilot',
            instructor='Dr. Example',
            duration_hours=8,
            difficulty='Beginner',
            description='Example course',
        )
        Enrollment.objects.create(user=self.user, course=self.course, progress_pct=65, status='in_progress')
        WellnessProtocol.objects.create(
            user=self.user,
            title='Personalized Recovery Protocol',
            biomarker_source='Wearable ring',
            status='synced',
        )
        MedicalReport.objects.create(
            user=self.user,
            title='User-specific EEG Report',
            document_type='EEG Diagnostic Report',
            encrypted_hash='0xabc',
        )
        MedicalReport.objects.create(
            user=self.user,
            title='Second User Report',
            document_type='fMRI Imaging Scan',
            encrypted_hash='0xdef',
        )
        HealthWalletTransaction.objects.create(
            transaction_id='TX-UNIQUE-001',
            amount=Decimal('125.00'),
            transaction_type='Reward',
            description='Neural reward',
            user=self.user,
        )
        CognitiveMetric.objects.create(
            user=self.user,
            date='2026-08-28',
            focus_retention=82.0,
            stress_level=31.0,
        )

    def test_myspace_uses_user_specific_data(self):
        self.client.force_login(self.user)

        response = self.client.get('/myspace/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['records_count'], 2)
        self.assertNotEqual(response.context['coverage_pct'], '94.2%')
        self.assertEqual(response.context['bench_active'], 2)
        self.assertEqual(response.context['fund_total'], '$125.00')


class FeatureHintTrackingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='hintuser',
            email='hintuser@example.com',
            password='secret123',
        )

    def test_tooltip_seen_is_recorded_for_user(self):
        self.assertFalse(UserFeatureHint.objects.filter(user=self.user, key='dashboard_overview').exists())

        hint = UserFeatureHint.objects.create(user=self.user, key='dashboard_overview', title='Dashboard overview', body='Use the cards to track your progress.')

        self.assertTrue(UserFeatureHint.objects.filter(user=self.user, key='dashboard_overview').exists())
        self.assertEqual(hint.user, self.user)


class ProfileInsightGenerationTests(TestCase):
    def test_generate_profile_insight_uses_profile_and_metric_context(self):
        user = get_user_model().objects.create_user(
            username='insightuser',
            email='insight@example.com',
            password='secret123',
        )
        profile = NeuroProfile.objects.create(
            user=user,
            full_name='Insight User',
            pathway='Research & Innovation',
            cognitive_goal='Memory & Concentration',
            data_processing_consent=True,
        )
        CognitiveMetric.objects.create(
            user=user,
            date='2026-08-29',
            focus_retention=42.0,
            stress_level=71.0,
        )

        insight = generate_profile_insight(
            profile,
            CognitiveMetric.objects.filter(user=user),
            reports=[{'title': 'EEG Report'}],
            goals=['memory', 'focus']
        )

        self.assertIn('Focus and recovery signals need attention', insight['headline'])
        self.assertTrue(any('stress load appears elevated' in flag for flag in insight['risk_flags']))
        self.assertTrue(any('pathway' in item for item in insight['opportunities']))
        self.assertTrue(insight['recommendations'])


class NotificationAndPlanRoutingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='notifyuser',
            email='notify@example.com',
            password='secret123',
        )

    def test_notification_badge_counts_unread_items(self):
        self.client.force_login(self.user)
        Notification.objects.create(user=self.user, message='Your plan is ready.', link_url='/select-plan/')
        Notification.objects.create(user=self.user, message='Check your wellness update.', link_url='/wellness/', is_read=True)

        response = self.client.get('/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1')
        self.assertContains(response, 'Notifications')

    def test_select_plan_page_loads(self):
        self.client.force_login(self.user)
        InsurancePlan = __import__('core.models', fromlist=['InsurancePlan']).InsurancePlan
        InsurancePlan.objects.create(name='Essential Care', monthly_premium='69.00', coverage_details='Basic coverage')

        response = self.client.get('/select-plan/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a plan')
        self.assertContains(response, 'Essential Care')


class MentalHealthAssessmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='mentaluser',
            email='mental@example.com',
            password='secret123',
        )

    def test_mental_health_screening_page_loads(self):
        self.client.force_login(self.user)

        response = self.client.get('/wellness/mental-health/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mental health check-in')

    def test_mental_health_screening_analysis_returns_fallback_result(self):
        self.client.force_login(self.user)

        response = self.client.post('/wellness/mental-health/', {
            'condition': 'Stress',
            'q1': 'Often',
            'q2': 'Sometimes',
            'q3': 'More than usual',
            'q4': 'Rarely',
            'q5': 'Often',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI insight')
        self.assertContains(response, 'Share these results with a qualified healthcare provider')

    def test_mental_health_screening_uses_branching_question_flow(self):
        self.client.force_login(self.user)

        response = self.client.post('/wellness/mental-health/', {
            'condition': 'Stress',
            'q1': 'Often',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'When responsibilities pile up')
        self.assertContains(response, 'What usually helps you feel more regulated')

    def test_mental_health_screening_resets_after_completion(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['mental_health_questionnaire'] = {
            'current_node': 'check_in_complete',
            'responses': {'q_initial_selection': 'Stress'},
            'return_to_node': 'q_initial_selection',
            'condition': 'Stress',
        }
        session.save()

        response = self.client.get('/wellness/mental-health/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mental health check-in')
        self.assertNotContains(response, 'AI insight')

    def test_mental_health_screening_restart_button_resets_stale_session(self):
        self.client.force_login(self.user)

        response = self.client.post('/wellness/mental-health/', {
            'condition': 'Stress',
            'current_node': 'check_in_complete',
            'restart_assessment': 'true',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mental health check-in')
        self.assertNotContains(response, 'AI insight')
