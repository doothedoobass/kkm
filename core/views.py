from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .models import *
from django.db import models, connection
import json
import hashlib
import logging
import os
import uuid
from statistics import mean

from django.conf import settings

logger = logging.getLogger(__name__)

FEATURE_HINT_LIBRARY = {
    'dashboard_overview': {
        'title': 'Dashboard overview',
        'body': 'Track your live Neurohealth signals, clinician readiness, and recent clinical uploads from this summary panel.',
        'anchor': '#dashboard-overview-card'
    },
    'dashboard_chart': {
        'title': 'Cognitive tracking',
        'body': 'This trend view shows your recent focus retention and stress baseline so you can monitor changes over time.',
        'anchor': '#dashboard-chart-panel'
    },
    'dashboard_reports': {
        'title': 'Clinical uploads',
        'body': 'Your latest e-MR records stay here for quick review, audit trail checks, and secure access to your care history.',
        'anchor': '#dashboard-reports-panel'
    },
    'myspace_overview': {
        'title': 'MySpace overview',
        'body': 'These cards summarize your personal coverage, record volume, active benchwork, and wallet activity for this account.',
        'anchor': '#myspace-overview-card'
    },
    'myspace_map': {
        'title': 'Global brain-health map',
        'body': 'The NBHDI map visualizes region-level health conditions so you can understand environmental and socioeconomic factors in context.',
        'anchor': '#myspace-map-panel'
    },
    'myspace_telemetry': {
        'title': 'Node telemetry feed',
        'body': 'Use this live feed to monitor recent regional events and operational signals across your connected health ecosystem.',
        'anchor': '#myspace-telemetry-panel'
    },
}


def get_unseen_feature_hints(request, keys):
    seen_keys = set(UserFeatureHint.objects.filter(user=request.user).values_list('key', flat=True))
    hints = []
    for key in keys:
        hint = FEATURE_HINT_LIBRARY.get(key)
        if hint and key not in seen_keys:
            hints.append({
                'key': key,
                'title': hint['title'],
                'body': hint['body'],
                'anchor': hint.get('anchor', None),
            })
    return hints


@login_required(login_url='login')
def feature_hint_mark_seen(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'message': 'Only POST requests are supported.'}, status=405)

    key = request.POST.get('key', '').strip()
    if not key or key not in FEATURE_HINT_LIBRARY:
        return JsonResponse({'ok': False, 'message': 'Invalid feature hint.'}, status=400)

    hint_data = FEATURE_HINT_LIBRARY[key]
    hint, created = UserFeatureHint.objects.get_or_create(
        user=request.user,
        key=key,
        defaults={'title': hint_data['title'], 'body': hint_data['body']}
    )
    return JsonResponse({'ok': True, 'created': created})

def ensure_medicalreport_schema():
    try:
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute("PRAGMA table_info(core_medicalreport);")
                columns = [row[1] for row in cursor.fetchall()]
                if columns and 'file' not in columns:
                    cursor.execute("ALTER TABLE core_medicalreport ADD COLUMN file varchar(100);")
                if columns and 'file_size' not in columns:
                    cursor.execute("ALTER TABLE core_medicalreport ADD COLUMN file_size varchar(50);")
    except Exception:
        pass

def get_current_profile(request=None):
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        return NeuroProfile.objects.filter(user=request.user).first()
    return None


def unread_notifications_context(request):
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        return {'unread_notifications_count': Notification.objects.filter(user=request.user, is_read=False).count()}
    return {'unread_notifications_count': 0}


def get_unread_notifications(request):
    if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
        return []
    return Notification.objects.filter(user=request.user, is_read=False)


@login_required(login_url='login')
def notifications(request):
    notifications_qs = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications_qs.filter(is_read=False).count()
    return render(request, 'notifications.html', {
        'profile': get_current_profile(request),
        'notifications': notifications_qs,
        'unread_count': unread_count,
    })


@login_required(login_url='login')
def notifications_mark_read(request):
    if request.method != 'POST':
        return redirect('notifications')

    notification_ids = request.POST.getlist('notification_ids')
    if notification_ids:
        Notification.objects.filter(user=request.user, id__in=notification_ids).update(is_read=True)
    else:
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    django_messages.success(request, 'Notifications marked as read.')
    return redirect('notifications')


@login_required(login_url='login')
def select_plan(request):
    plans = InsurancePlan.objects.filter(is_active=True)
    return render(request, 'select_plan.html', {
        'profile': get_current_profile(request),
        'plans': plans,
    })


def generate_profile_insight(profile, metrics, reports=None, goals=None):
    """
    Build a personalized insight summary for a user profile using lightweight,
    behavior-based analysis over the current NeuroProfile and recent metric data.
    """
    if not profile:
        return {
            'headline': 'Profile not ready for a full insight review.',
            'summary': 'Add a profile and activity data to unlock personalized recommendations.',
            'risk_flags': [],
            'opportunities': [],
            'recommendations': [],
        }

    metrics = list(metrics or [])
    reports = list(reports or [])
    goals = list(goals or [])

    focus_values = []
    stress_values = []
    mood_values = []
    energy_values = []

    for item in metrics:
        if hasattr(item, 'focus_retention'):
            focus_values.append(float(item.focus_retention))
        if hasattr(item, 'stress_level'):
            stress_values.append(float(item.stress_level))
        if hasattr(item, 'mood_score'):
            mood_values.append(float(item.mood_score))
        if hasattr(item, 'energy_score'):
            energy_values.append(float(item.energy_score))

    avg_focus = round(mean(focus_values), 1) if focus_values else None
    avg_stress = round(mean(stress_values), 1) if stress_values else None
    avg_mood = round(mean(mood_values), 1) if mood_values else None
    avg_energy = round(mean(energy_values), 1) if energy_values else None

    risk_flags = []
    opportunities = []
    recommendations = []

    if avg_focus is not None:
        if avg_focus < 55:
            risk_flags.append('focus retention is trending below the expected range')
        else:
            opportunities.append('cognitive consistency looks stable across recent activity')

    if avg_stress is not None:
        if avg_stress > 60:
            risk_flags.append('stress load appears elevated over the recent period')
        else:
            opportunities.append('stress management appears relatively controlled')

    if avg_mood is not None:
        if avg_mood < 45:
            risk_flags.append('mood indicators suggest increased emotional strain')
        elif avg_mood > 70:
            opportunities.append('mood stability is a strength worth reinforcing')

    if avg_energy is not None:
        if avg_energy < 50:
            risk_flags.append('energy levels may be limiting daily resilience')
        else:
            opportunities.append('energy support appears healthy and sustainable')

    if len(reports) == 0:
        opportunities.append('no recent clinical exports are attached yet')
    elif len(reports) >= 2:
        opportunities.append('clinical history has sufficient depth for trend tracking')

    if getattr(profile, 'pathway', None):
        opportunities.append(f"career pathway '{profile.pathway}' may benefit from a more targeted wellbeing plan")

    if goals:
        topic_list = ', '.join(str(goal) for goal in goals[:3])
        opportunities.append(f"goal alignment is strongest when the plan supports: {topic_list}")

    if risk_flags:
        headline = 'Focus and recovery signals need attention'
    elif opportunities:
        headline = 'Your profile shows promising patterns and a few leverage points'
    else:
        headline = 'Your profile is stable and ready for continued monitoring'

    if 'focus retention is trending below the expected range' in risk_flags:
        recommendations.append('Introduce short, structured focus blocks and reduce task switching during high-load periods.')

    if 'stress load appears elevated over the recent period' in risk_flags:
        recommendations.append('Use a lower-cognitive-load schedule and build recovery periods into the week.')

    if 'mood indicators suggest increased emotional strain' in risk_flags:
        recommendations.append('Prioritize emotional recovery, support-seeking, and sleep consistency to stabilize mood outcomes.')

    if 'energy levels may be limiting daily resilience' in risk_flags:
        recommendations.append('Review workload intensity, recovery timing, and daily routines that may be draining energy.')

    if not recommendations:
        recommendations.append('Maintain the current rhythm and continue tracking trends over the next few cycles.')

    if getattr(profile, 'cognitive_goal', None):
        recommendations.append(f"Keep the plan centered on '{profile.cognitive_goal}' to maintain momentum.")

    if getattr(profile, 'pathway', None):
        recommendations.append(f"Use your '{profile.pathway}' pathway as a decision lens for matching resources and routines.")

    stress_label = 'balanced' if avg_stress is not None and avg_stress <= 60 else 'higher' if avg_stress is not None else 'mixed'
    summary = (
        f"Based on {len(metrics) or 'limited'} recent data points "
        f"and the current profile context, the chart suggests a {stress_label} stress pattern."
    )

    return {
        'headline': headline,
        'summary': summary,
        'risk_flags': risk_flags,
        'opportunities': opportunities,
        'recommendations': recommendations[:5],
    }


def fallback_mental_health_analysis(condition, answers):
    summary = (
        "Thank you for completing this check-in. The experiences you described suggest that stress, low mood, or emotional strain may be affecting your day-to-day life. "
        "This screening is not a diagnosis, but it highlights patterns that are often associated with mental health challenges like {}."
    ).format(condition)
    next_steps = [
        'Share these results with a qualified healthcare provider or mental health professional for an accurate diagnosis and personalized advice.',
        'Talk to a trusted friend, family member, or mentor about what you are experiencing.',
        'Review reputable mental health resources such as NAMI, Mind, or the National Institute of Mental Health for trusted guidance.',
        'Track your mood, sleep, and energy in a short journal to notice patterns over time.',
        'Give yourself patience and compassion while you build a support plan that feels sustainable.'
    ]
    return {
        'analysis': summary,
        'next_steps': next_steps,
    }


MENTAL_HEALTH_QUESTIONNAIRE = {
    'questionnaire': 'Comprehensive Mental Health Intake',
    'version': '1.0',
    'disclaimer': 'This tool is a self-report screener, not a diagnostic instrument. It does not diagnose any condition. Results should be reviewed by a licensed clinician before any treatment decision is made.',
    'start_node': 'q_initial_selection',
    'crisis_resources': {
        'us': {
            'call_or_text': '988',
            'name': '988 Suicide & Crisis Lifeline',
            'text_line': 'Text HOME to 741741 (Crisis Text Line)'
        },
        'international_note': 'If outside the US, direct users to their local emergency number or findahelpline.com'
    },
    'nodes': {
        'q_initial_selection': {
            'id': 'q_initial_selection',
            'text': 'Which of the following best describes your primary concern right now?',
            'type': 'single_choice',
            'options': [
                {'label': 'Stress', 'next_node': 'stress_q1'},
                {'label': 'Anxiety', 'next_node': 'anx_q1'},
                {'label': 'Depression / low mood', 'next_node': 'dep_q1'},
                {'label': 'Burnout', 'next_node': 'burn_q1'},
                {'label': 'Sleep difficulties', 'next_node': 'sleep_q1'},
            ],
        },
        'safety_check': {
            'id': 'safety_check',
            'text': "Before we continue: in the past two weeks, have you had any thoughts of harming yourself or that life isn't worth living?",
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'RETURN_TO_TRACK', 'score': 0},
                {'label': 'Yes', 'next_node': 'crisis_intervention', 'score': 5},
            ],
            'note': 'This node is injected at a fixed point in every track. RETURN_TO_TRACK is a placeholder your engine should resolve to the node the user came from.'
        },
        'crisis_intervention': {
            'id': 'crisis_intervention',
            'type': 'endpoint_alert',
            'text': "It sounds like things are very hard right now. Your safety matters most. Please reach out to a crisis line immediately: call or text 988 (Suicide & Crisis Lifeline), or text HOME to 741741 (Crisis Text Line). If you're in immediate danger, call your local emergency number.",
            'action': 'trigger_safety_protocol',
            'blocking': True,
        },
        'stress_q1': {
            'id': 'stress_q1',
            'text': 'How often do you feel overwhelmed by everyday responsibilities?',
            'type': 'single_choice',
            'options': [
                {'label': 'Rarely', 'next_node': 'stress_q2_mild', 'score': 0},
                {'label': 'Sometimes', 'next_node': 'stress_q2_moderate', 'score': 1},
                {'label': 'Often or always', 'next_node': 'stress_q2_severe', 'score': 3},
            ],
        },
        'stress_q2_severe': {
            'id': 'stress_q2_severe',
            'text': 'Are you noticing physical symptoms like a racing heart, headaches, or muscle tension?',
            'type': 'single_choice',
            'options': [
                {'label': 'Yes, frequently', 'next_node': 'stress_q3_control', 'score': 2},
                {'label': 'No, mostly emotional', 'next_node': 'stress_q3_control', 'score': 0},
            ],
        },
        'stress_q2_moderate': {
            'id': 'stress_q2_moderate',
            'text': 'Do these feelings come and go, or are they fairly constant?',
            'type': 'single_choice',
            'options': [
                {'label': 'Come and go', 'next_node': 'stress_q3_control', 'score': 1},
                {'label': 'Fairly constant', 'next_node': 'stress_q3_control', 'score': 2},
            ],
        },
        'stress_q2_mild': {
            'id': 'stress_q2_mild',
            'text': 'Do you feel you have effective ways to decompress after a busy day?',
            'type': 'single_choice',
            'options': [
                {'label': 'Yes, usually', 'next_node': 'stress_q3_control', 'score': 0},
                {'label': 'No, I struggle to relax', 'next_node': 'stress_q3_control', 'score': 1},
            ],
        },
        'stress_q3_control': {
            'id': 'stress_q3_control',
            'text': 'How often do you feel unable to control the important things in your life?',
            'type': 'single_choice',
            'options': [
                {'label': 'Never', 'next_node': 'stress_q4_triggers', 'score': 0},
                {'label': 'Sometimes', 'next_node': 'stress_q4_triggers', 'score': 1},
                {'label': 'Often', 'next_node': 'stress_q4_triggers', 'score': 2},
            ],
        },
        'stress_q4_triggers': {
            'id': 'stress_q4_triggers',
            'text': 'What is the primary source of your stress right now?',
            'type': 'single_choice',
            'options': [
                {'label': 'Work or career', 'next_node': 'stress_q5_work'},
                {'label': 'Family or relationships', 'next_node': 'stress_q5_personal'},
                {'label': 'Financial', 'next_node': 'stress_q5_personal'},
                {'label': 'Health concerns', 'next_node': 'stress_q5_personal'},
            ],
        },
        'stress_q5_work': {
            'id': 'stress_q5_work',
            'text': 'Is your work stress mainly about workload, or interpersonal conflict?',
            'type': 'single_choice',
            'options': [
                {'label': 'Workload and hours', 'next_node': 'stress_q6_support', 'score': 1},
                {'label': 'Interpersonal conflict', 'next_node': 'stress_q6_support', 'score': 1},
            ],
        },
        'stress_q5_personal': {
            'id': 'stress_q5_personal',
            'text': 'Do you feel you have people you can lean on for this?',
            'type': 'single_choice',
            'options': [
                {'label': 'Yes, a strong support system', 'next_node': 'stress_q6_support', 'score': -1},
                {'label': 'No, I feel fairly isolated', 'next_node': 'stress_q6_support', 'score': 2},
            ],
        },
        'stress_q6_support': {
            'id': 'stress_q6_support',
            'text': 'How often do you feel confident about your ability to handle personal problems?',
            'type': 'single_choice',
            'options': [
                {'label': 'Fairly often', 'next_node': 'stress_q7_coping', 'score': 0},
                {'label': 'Sometimes', 'next_node': 'stress_q7_coping', 'score': 1},
                {'label': 'Rarely or never', 'next_node': 'stress_q7_coping', 'score': 2},
            ],
        },
        'stress_q7_coping': {
            'id': 'stress_q7_coping',
            'text': 'In the past two weeks, how have you mostly been coping with this stress?',
            'type': 'multiple_choice',
            'options': [
                {'label': 'Exercise or hobbies', 'next_node': 'stress_q8_irritability', 'score': 0},
                {'label': 'Eating more or less than usual', 'next_node': 'stress_q8_irritability', 'score': 1},
                {'label': 'Using alcohol or substances', 'next_node': 'stress_q8_irritability', 'score': 2},
                {'label': 'Withdrawing from people', 'next_node': 'stress_q8_irritability', 'score': 2},
            ],
        },
        'stress_q8_irritability': {
            'id': 'stress_q8_irritability',
            'text': 'Have you noticed yourself getting irritated or angry more easily than usual?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'stress_q9_duration', 'score': 0},
                {'label': 'Yes, somewhat', 'next_node': 'stress_q9_duration', 'score': 1},
                {'label': 'Yes, significantly', 'next_node': 'stress_q9_duration', 'score': 2},
            ],
        },
        'stress_q9_duration': {
            'id': 'stress_q9_duration',
            'text': 'How long have you been feeling this level of stress?',
            'type': 'single_choice',
            'options': [
                {'label': 'Less than a month', 'next_node': 'stress_q10_concentration', 'score': 0},
                {'label': '1 to 6 months', 'next_node': 'stress_q10_concentration', 'score': 1},
                {'label': 'More than 6 months', 'next_node': 'stress_q10_concentration', 'score': 2},
            ],
        },
        'stress_q10_concentration': {
            'id': 'stress_q10_concentration',
            'text': 'Is this stress making it hard to concentrate or make decisions?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'stress_q11_sleep', 'score': 0},
                {'label': 'Yes', 'next_node': 'stress_q11_sleep', 'score': 1},
            ],
        },
        'stress_q11_sleep': {
            'id': 'stress_q11_sleep',
            'text': 'Is this stress making it difficult to fall asleep or stay asleep?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'safety_check', 'score': 0},
                {'label': 'Yes', 'next_node': 'sleep_q1', 'score': 1, 'cross_branch': True},
            ],
        },
        'result_stress_evaluation': {
            'id': 'result_stress_evaluation',
            'type': 'endpoint',
            'text': 'Based on your responses, here is your stress profile.',
            'action': 'calculate_final_score',
            'score_bands': [
                {'range': [0, 6], 'label': 'Low', 'recommendation_id': 'rec_general_wellness'},
                {'range': [7, 14], 'label': 'Moderate', 'recommendation_id': 'rec_stress_management'},
                {'range': [15, 24], 'label': 'High', 'recommendation_id': 'rec_therapy_and_medical_check'},
            ],
        },
        'burn_q1': {
            'id': 'burn_q1',
            'text': 'How often do you feel emotionally drained by your work or main daily role?',
            'type': 'single_choice',
            'options': [
                {'label': 'Never', 'next_node': 'burn_q2_exhaustion', 'score': 0},
                {'label': 'Sometimes', 'next_node': 'burn_q2_exhaustion', 'score': 1},
                {'label': 'Often or daily', 'next_node': 'burn_q2_exhaustion', 'score': 2},
            ],
        },
        'burn_q2_exhaustion': {
            'id': 'burn_q2_exhaustion',
            'text': 'Do you wake up already feeling tired at the thought of the day ahead?',
            'type': 'single_choice',
            'options': [
                {'label': 'Rarely', 'next_node': 'burn_q3_cynicism', 'score': 0},
                {'label': 'Often', 'next_node': 'burn_q3_cynicism', 'score': 2},
            ],
        },
        'burn_q3_cynicism': {
            'id': 'burn_q3_cynicism',
            'text': 'Have you become more cynical or detached about your work than you used to be?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'burn_q4_efficacy', 'score': 0},
                {'label': 'Somewhat', 'next_node': 'burn_q4_efficacy', 'score': 1},
                {'label': 'Significantly', 'next_node': 'burn_q4_efficacy', 'score': 2},
            ],
        },
        'burn_q4_efficacy': {
            'id': 'burn_q4_efficacy',
            'text': 'Do you feel less effective or accomplished in your role than you used to?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'burn_q5_workload', 'score': 0},
                {'label': 'Yes', 'next_node': 'burn_q5_workload', 'score': 1},
            ],
        },
        'burn_q5_workload': {
            'id': 'burn_q5_workload',
            'text': 'Does your workload feel sustainable, or constantly overwhelming?',
            'type': 'single_choice',
            'options': [
                {'label': 'Sustainable', 'next_node': 'burn_q6_control', 'score': 0},
                {'label': 'Constantly overwhelming', 'next_node': 'burn_q6_control', 'score': 2},
            ],
        },
        'burn_q6_control': {
            'id': 'burn_q6_control',
            'text': 'Do you feel you have enough control or say over how you do your work?',
            'type': 'single_choice',
            'options': [
                {'label': 'Yes', 'next_node': 'burn_q7_recognition', 'score': 0},
                {'label': 'No', 'next_node': 'burn_q7_recognition', 'score': 1},
            ],
        },
        'burn_q7_recognition': {
            'id': 'burn_q7_recognition',
            'text': 'Do you feel your effort is fairly recognized or rewarded?',
            'type': 'single_choice',
            'options': [
                {'label': 'Yes', 'next_node': 'burn_q8_values', 'score': 0},
                {'label': 'No', 'next_node': 'burn_q8_values', 'score': 1},
            ],
        },
        'burn_q8_values': {
            'id': 'burn_q8_values',
            'text': 'Do you feel your work still aligns with what matters to you personally?',
            'type': 'single_choice',
            'options': [
                {'label': 'Yes', 'next_node': 'burn_q9_physical', 'score': 0},
                {'label': 'No, it feels disconnected', 'next_node': 'burn_q9_physical', 'score': 1},
            ],
        },
        'burn_q9_physical': {
            'id': 'burn_q9_physical',
            'text': 'Have you had more physical complaints lately (headaches, stomach issues, getting sick more often)?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'burn_q10_withdrawal', 'score': 0},
                {'label': 'Yes', 'next_node': 'burn_q10_withdrawal', 'score': 1},
            ],
        },
        'burn_q10_withdrawal': {
            'id': 'burn_q10_withdrawal',
            'text': 'Have you been withdrawing from colleagues, friends, or family because of exhaustion?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'burn_q11_sleep', 'score': 0},
                {'label': 'Yes', 'next_node': 'burn_q11_sleep', 'score': 1},
            ],
        },
        'burn_q11_sleep': {
            'id': 'burn_q11_sleep',
            'text': 'Has this affected your sleep quality?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'burn_q12_duration', 'score': 0},
                {'label': 'Yes', 'next_node': 'sleep_q1', 'score': 1, 'cross_branch': True},
            ],
        },
        'burn_q12_duration': {
            'id': 'burn_q12_duration',
            'text': 'How long has this been building?',
            'type': 'single_choice',
            'options': [
                {'label': 'Less than a month', 'next_node': 'safety_check', 'score': 0},
                {'label': '1 to 6 months', 'next_node': 'safety_check', 'score': 1},
                {'label': 'More than 6 months', 'next_node': 'safety_check', 'score': 2},
            ],
        },
        'sleep_q1': {
            'id': 'sleep_q1',
            'text': 'What sleep difficulty are you experiencing most?',
            'type': 'single_choice',
            'options': [
                {'label': 'Trouble falling asleep', 'next_node': 'sleep_q2_onset', 'score': 1},
                {'label': 'Waking during the night', 'next_node': 'sleep_q2_maintenance', 'score': 1},
                {'label': 'Waking too early', 'next_node': 'sleep_q2_early', 'score': 1},
                {'label': 'Sleeping too much', 'next_node': 'sleep_q2_hypersomnia', 'score': 1},
            ],
        },
        'sleep_q2_onset': {
            'id': 'sleep_q2_onset',
            'text': 'On average, how long does it take you to fall asleep?',
            'type': 'single_choice',
            'options': [
                {'label': 'Under 30 minutes', 'next_node': 'sleep_q3_frequency', 'score': 0},
                {'label': '30 to 60 minutes', 'next_node': 'sleep_q3_frequency', 'score': 1},
                {'label': 'Over an hour', 'next_node': 'sleep_q3_frequency', 'score': 2},
            ],
        },
        'sleep_q2_maintenance': {
            'id': 'sleep_q2_maintenance',
            'text': 'How many times do you typically wake during the night?',
            'type': 'single_choice',
            'options': [
                {'label': '0 to 1', 'next_node': 'sleep_q3_frequency', 'score': 0},
                {'label': '2 to 3', 'next_node': 'sleep_q3_frequency', 'score': 1},
                {'label': '4 or more', 'next_node': 'sleep_q3_frequency', 'score': 2},
            ],
        },
        'sleep_q2_early': {
            'id': 'sleep_q2_early',
            'text': 'How much earlier than desired are you waking up?',
            'type': 'single_choice',
            'options': [
                {'label': 'Less than 30 minutes', 'next_node': 'sleep_q3_frequency', 'score': 0},
                {'label': '30 minutes to an hour', 'next_node': 'sleep_q3_frequency', 'score': 1},
                {'label': 'More than an hour', 'next_node': 'sleep_q3_frequency', 'score': 2},
            ],
        },
        'sleep_q2_hypersomnia': {
            'id': 'sleep_q2_hypersomnia',
            'text': 'On average, how many hours are you sleeping per night now, compared to your usual?',
            'type': 'single_choice',
            'options': [
                {'label': 'About 1 extra hour', 'next_node': 'sleep_q3_frequency', 'score': 1},
                {'label': '2 or more extra hours', 'next_node': 'sleep_q3_frequency', 'score': 2},
            ],
        },
        'sleep_q3_frequency': {
            'id': 'sleep_q3_frequency',
            'text': 'How many nights per week does this happen?',
            'type': 'single_choice',
            'options': [
                {'label': '1 to 2 nights', 'next_node': 'sleep_q4_duration', 'score': 0},
                {'label': '3 to 4 nights', 'next_node': 'sleep_q4_duration', 'score': 1},
                {'label': '5 or more nights', 'next_node': 'sleep_q4_duration', 'score': 2},
            ],
        },
        'sleep_q4_duration': {
            'id': 'sleep_q4_duration',
            'text': 'How long has this pattern been going on?',
            'type': 'single_choice',
            'options': [
                {'label': 'Less than a month', 'next_node': 'sleep_q5_daytime', 'score': 0},
                {'label': '1 to 3 months', 'next_node': 'sleep_q5_daytime', 'score': 1},
                {'label': 'More than 3 months', 'next_node': 'sleep_q5_daytime', 'score': 2},
            ],
        },
        'sleep_q5_daytime': {
            'id': 'sleep_q5_daytime',
            'text': 'How much does poor sleep affect your daytime functioning (focus, mood, energy)?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'sleep_q6_habits', 'score': 0},
                {'label': 'Somewhat', 'next_node': 'sleep_q6_habits', 'score': 1},
                {'label': 'A great deal', 'next_node': 'sleep_q6_habits', 'score': 2},
            ],
        },
        'sleep_q6_habits': {
            'id': 'sleep_q6_habits',
            'text': 'Do you use screens, caffeine, or alcohol close to bedtime?',
            'type': 'multiple_choice',
            'options': [
                {'label': 'Screens', 'next_node': 'sleep_q7_worry', 'score': 1},
                {'label': 'Caffeine', 'next_node': 'sleep_q7_worry', 'score': 1},
                {'label': 'Alcohol', 'next_node': 'sleep_q7_worry', 'score': 1},
                {'label': 'None of these', 'next_node': 'sleep_q7_worry', 'score': 0},
            ],
        },
        'sleep_q7_worry': {
            'id': 'sleep_q7_worry',
            'text': 'Do you find yourself lying awake worrying or with racing thoughts?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'sleep_q8_satisfaction', 'score': 0},
                {'label': 'Yes', 'next_node': 'sleep_q8_satisfaction', 'score': 1},
            ],
        },
        'sleep_q8_satisfaction': {
            'id': 'sleep_q8_satisfaction',
            'text': 'Overall, how satisfied are you with your current sleep?',
            'type': 'single_choice',
            'options': [
                {'label': 'Satisfied', 'next_node': 'sleep_q9_worried_about_sleep', 'score': 0},
                {'label': 'Dissatisfied', 'next_node': 'sleep_q9_worried_about_sleep', 'score': 1},
                {'label': 'Very dissatisfied', 'next_node': 'sleep_q9_worried_about_sleep', 'score': 2},
            ],
        },
        'sleep_q9_worried_about_sleep': {
            'id': 'sleep_q9_worried_about_sleep',
            'text': 'How worried are you about your current sleep pattern itself?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not worried', 'next_node': 'safety_check', 'score': 0},
                {'label': 'Somewhat worried', 'next_node': 'safety_check', 'score': 1},
                {'label': 'Very worried', 'next_node': 'safety_check', 'score': 2},
            ],
        },
        'result_sleep_evaluation': {
            'id': 'result_sleep_evaluation',
            'type': 'endpoint',
            'text': 'Based on your responses, here is your sleep profile.',
            'action': 'calculate_final_score',
            'score_bands': [
                {'range': [0, 5], 'label': 'No clinically significant insomnia', 'recommendation_id': 'rec_general_wellness'},
                {'range': [6, 11], 'label': 'Subthreshold insomnia', 'recommendation_id': 'rec_stress_management'},
                {'range': [12, 18], 'label': 'Moderate to severe insomnia', 'recommendation_id': 'rec_therapy_and_medical_check'},
            ],
        },
        'anx_q1': {
            'id': 'anx_q1',
            'text': 'Over the last two weeks, how often have you felt nervous, anxious, or on edge?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'anx_q2_worry', 'score': 0},
                {'label': 'Several days', 'next_node': 'anx_q2_worry', 'score': 1},
                {'label': 'More than half the days', 'next_node': 'anx_q2_worry', 'score': 2},
                {'label': 'Nearly every day', 'next_node': 'anx_q2_worry', 'score': 3},
            ],
        },
        'anx_q2_worry': {
            'id': 'anx_q2_worry',
            'text': 'How often have you found it hard to stop or control worrying?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'anx_q3_topics', 'score': 0},
                {'label': 'Several days', 'next_node': 'anx_q3_topics', 'score': 1},
                {'label': 'More than half the days', 'next_node': 'anx_q3_topics', 'score': 2},
                {'label': 'Nearly every day', 'next_node': 'anx_q3_topics', 'score': 3},
            ],
        },
        'anx_q3_topics': {
            'id': 'anx_q3_topics',
            'text': 'Is your worry focused on specific things (health, money, work) or does it feel more free-floating?',
            'type': 'single_choice',
            'options': [
                {'label': 'Specific things', 'next_node': 'anx_q4_physical', 'score': 1},
                {'label': 'Free-floating, hard to pin down', 'next_node': 'anx_q4_physical', 'score': 2},
            ],
        },
        'anx_q4_physical': {
            'id': 'anx_q4_physical',
            'text': 'Have you experienced physical symptoms like a racing heart, sweating, or trembling without clear cause?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q5_avoidance', 'score': 0},
                {'label': 'Occasionally', 'next_node': 'anx_q5_avoidance', 'score': 1},
                {'label': 'Frequently', 'next_node': 'anx_panic_check', 'score': 2},
            ],
        },
        'anx_panic_check': {
            'id': 'anx_panic_check',
            'text': 'Have any of these episodes felt sudden and intense, like a wave of fear peaking within minutes?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q5_avoidance', 'score': 0},
                {'label': 'Yes', 'next_node': 'anx_q5_avoidance', 'score': 2, 'flag': 'possible_panic_attacks'},
            ],
        },
        'anx_q5_avoidance': {
            'id': 'anx_q5_avoidance',
            'text': 'Have you started avoiding places, people, or situations because of anxiety?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q6_restlessness', 'score': 0},
                {'label': 'A little', 'next_node': 'anx_q6_restlessness', 'score': 1},
                {'label': 'Significantly', 'next_node': 'anx_q6_restlessness', 'score': 2},
            ],
        },
        'anx_q6_restlessness': {
            'id': 'anx_q6_restlessness',
            'text': 'How often have you felt restless or found it hard to sit still?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'anx_q7_fatigue', 'score': 0},
                {'label': 'Several days', 'next_node': 'anx_q7_fatigue', 'score': 1},
                {'label': 'Nearly every day', 'next_node': 'anx_q7_fatigue', 'score': 2},
            ],
        },
        'anx_q7_fatigue': {
            'id': 'anx_q7_fatigue',
            'text': 'Have you been feeling easily fatigued?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q8_irritable', 'score': 0},
                {'label': 'Yes', 'next_node': 'anx_q8_irritable', 'score': 1},
            ],
        },
        'anx_q8_irritable': {
            'id': 'anx_q8_irritable',
            'text': 'Have you been more irritable than usual?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q9_concentration', 'score': 0},
                {'label': 'Yes', 'next_node': 'anx_q9_concentration', 'score': 1},
            ],
        },
        'anx_q9_concentration': {
            'id': 'anx_q9_concentration',
            'text': 'Have you had trouble concentrating because your mind keeps jumping to worries?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q10_muscle', 'score': 0},
                {'label': 'Yes', 'next_node': 'anx_q10_muscle', 'score': 1},
            ],
        },
        'anx_q10_muscle': {
            'id': 'anx_q10_muscle',
            'text': 'Have you noticed muscle tension (jaw clenching, shoulder tightness, headaches)?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q11_sleep', 'score': 0},
                {'label': 'Yes', 'next_node': 'anx_q11_sleep', 'score': 1},
            ],
        },
        'anx_q11_sleep': {
            'id': 'anx_q11_sleep',
            'text': 'Has anxiety disrupted your sleep, either falling asleep or staying asleep?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'anx_q12_impact', 'score': 0},
                {'label': 'Yes', 'next_node': 'sleep_q1', 'score': 1, 'cross_branch': True},
            ],
        },
        'anx_q12_impact': {
            'id': 'anx_q12_impact',
            'text': 'How much has this anxiety interfered with work, school, or relationships?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'safety_check', 'score': 0},
                {'label': 'Somewhat', 'next_node': 'safety_check', 'score': 1},
                {'label': 'A great deal', 'next_node': 'safety_check', 'score': 2},
            ],
        },
        'dep_q1': {
            'id': 'dep_q1',
            'text': 'Over the last two weeks, how often have you felt down, low, or hopeless?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'dep_q2_interest', 'score': 0},
                {'label': 'Several days', 'next_node': 'dep_q2_interest', 'score': 1},
                {'label': 'More than half the days', 'next_node': 'dep_q2_interest', 'score': 2},
                {'label': 'Nearly every day', 'next_node': 'dep_q2_interest', 'score': 3},
            ],
        },
        'dep_q2_interest': {
            'id': 'dep_q2_interest',
            'text': 'How often have you had little interest or pleasure in doing things you\'d normally enjoy?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'dep_q3_sleep', 'score': 0},
                {'label': 'Several days', 'next_node': 'dep_q3_sleep', 'score': 1},
                {'label': 'More than half the days', 'next_node': 'dep_q3_sleep', 'score': 2},
                {'label': 'Nearly every day', 'next_node': 'dep_q3_sleep', 'score': 3},
            ],
        },
        'dep_q3_sleep': {
            'id': 'dep_q3_sleep',
            'text': 'Have you had trouble falling asleep, staying asleep, or sleeping too much?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'dep_q4_energy', 'score': 0},
                {'label': 'Yes', 'next_node': 'sleep_q1', 'score': 1, 'cross_branch': True},
            ],
        },
        'dep_q4_energy': {
            'id': 'dep_q4_energy',
            'text': 'How often have you felt tired or had little energy?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'dep_q5_appetite', 'score': 0},
                {'label': 'Several days', 'next_node': 'dep_q5_appetite', 'score': 1},
                {'label': 'Nearly every day', 'next_node': 'dep_q5_appetite', 'score': 2},
            ],
        },
        'dep_q5_appetite': {
            'id': 'dep_q5_appetite',
            'text': 'Has your appetite changed noticeably — eating much more or much less than usual?',
            'type': 'single_choice',
            'options': [
                {'label': 'No change', 'next_node': 'dep_q6_selfworth', 'score': 0},
                {'label': 'Yes, a change', 'next_node': 'dep_q6_selfworth', 'score': 1},
            ],
        },
        'dep_q6_selfworth': {
            'id': 'dep_q6_selfworth',
            'text': 'How often have you felt bad about yourself, or that you\'ve let yourself or your family down?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'dep_q7_concentration', 'score': 0},
                {'label': 'Several days', 'next_node': 'dep_q7_concentration', 'score': 1},
                {'label': 'Nearly every day', 'next_node': 'dep_q7_concentration', 'score': 2},
            ],
        },
        'dep_q7_concentration': {
            'id': 'dep_q7_concentration',
            'text': 'Have you had trouble concentrating on things like reading or watching TV?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'dep_q8_psychomotor', 'score': 0},
                {'label': 'Several days', 'next_node': 'dep_q8_psychomotor', 'score': 1},
                {'label': 'Nearly every day', 'next_node': 'dep_q8_psychomotor', 'score': 2},
            ],
        },
        'dep_q8_psychomotor': {
            'id': 'dep_q8_psychomotor',
            'text': 'Have others noticed you moving or speaking more slowly than usual, or the opposite — more restless and fidgety than usual?',
            'type': 'single_choice',
            'options': [
                {'label': 'No', 'next_node': 'dep_q9_selfharm', 'score': 0},
                {'label': 'Yes', 'next_node': 'dep_q9_selfharm', 'score': 1},
            ],
        },
        'dep_q9_selfharm': {
            'id': 'dep_q9_selfharm',
            'text': 'How often have you had thoughts that you\'d be better off dead, or of hurting yourself in some way?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not at all', 'next_node': 'dep_q10_duration', 'score': 0},
                {'label': 'Several days', 'next_node': 'crisis_intervention', 'score': 4},
                {'label': 'More than half the days', 'next_node': 'crisis_intervention', 'score': 5},
                {'label': 'Nearly every day', 'next_node': 'crisis_intervention', 'score': 6},
            ],
        },
        'dep_q10_duration': {
            'id': 'dep_q10_duration',
            'text': 'How long have you felt this way?',
            'type': 'single_choice',
            'options': [
                {'label': 'Less than 2 weeks', 'next_node': 'dep_q11_function', 'score': 0},
                {'label': '2 weeks to a few months', 'next_node': 'dep_q11_function', 'score': 1},
                {'label': 'Longer than that', 'next_node': 'dep_q11_function', 'score': 2},
            ],
        },
        'dep_q11_function': {
            'id': 'dep_q11_function',
            'text': 'How much have these feelings made it hard to do your work, take care of things at home, or get along with others?',
            'type': 'single_choice',
            'options': [
                {'label': 'Not difficult at all', 'next_node': 'safety_check', 'score': 0},
                {'label': 'Somewhat difficult', 'next_node': 'safety_check', 'score': 1},
                {'label': 'Very or extremely difficult', 'next_node': 'safety_check', 'score': 2},
            ],
        },
    },
    'recommendations': {
        'rec_general_wellness': {
            'summary': 'Your responses suggest low current symptom burden.',
            'suggested_actions': ['Maintain current coping habits', 'Revisit this screener periodically'],
        },
        'rec_stress_management': {
            'summary': 'Your responses suggest mild to moderate symptoms.',
            'suggested_actions': ['Consider stress-management resources', 'Talk to a counselor or your doctor if symptoms persist'],
        },
        'rec_therapy_and_medical_check': {
            'summary': 'Your responses suggest a level of symptoms worth discussing with a professional.',
            'suggested_actions': ['Schedule an appointment with a therapist or doctor', 'Consider a full clinical evaluation'],
        },
        'rec_urgent_professional_referral': {
            'summary': 'Your responses suggest significant symptom burden.',
            'suggested_actions': ['Seek professional evaluation soon', 'If any thoughts of self-harm arise, use crisis resources immediately'],
        },
    },
}


def _get_questionnaire_node(node_id):
    return MENTAL_HEALTH_QUESTIONNAIRE['nodes'].get(node_id, {
        'id': node_id,
        'type': 'endpoint',
        'text': 'Thanks for completing this check-in. Your responses are ready to review.',
        'options': [],
    })


def _resolve_questionnaire_transition(node, selected_option, state):
    if not node:
        return state.get('current_node', MENTAL_HEALTH_QUESTIONNAIRE['start_node'])

    for option in node.get('options', []):
        if option.get('label') == selected_option:
            next_node = option.get('next_node')
            if next_node == 'RETURN_TO_TRACK':
                return state.get('return_to_node') or MENTAL_HEALTH_QUESTIONNAIRE['start_node']
            return next_node or state.get('current_node', MENTAL_HEALTH_QUESTIONNAIRE['start_node'])

    return state.get('current_node', MENTAL_HEALTH_QUESTIONNAIRE['start_node'])


def parse_gemini_analysis(text):
    if not text:
        return None
    try:
        clean_text = text.strip()
        if clean_text.startswith('```'):
            clean_text = clean_text.replace('```json', '', 1).replace('```', '', 1).strip()
        payload = json.loads(clean_text)
        if isinstance(payload, dict):
            analysis = payload.get('analysis') or payload.get('summary')
            next_steps = payload.get('next_steps') or payload.get('nextSteps') or []
            if analysis:
                return {'analysis': analysis, 'next_steps': list(next_steps) if next_steps else fallback_mental_health_analysis('your selected condition', {}).get('next_steps')}
    except Exception:
        pass
    return None


def generate_mental_health_analysis(condition, answers):
    prompt = (
        "You are an empathetic and supportive AI mental health assistant. Provide a brief non-diagnostic analysis and 3-5 next steps. "
        f"User is screening for: {condition}. Answers: {json.dumps(answers, ensure_ascii=False)}. "
        "Return valid JSON only with keys 'analysis' and 'next_steps'. "
        "Ensure the first next step is exactly: 'Share these results with a qualified healthcare provider or mental health professional for an accurate diagnosis and personalized advice.'"
    )

    api_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_API_KEY', '') or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            text = getattr(response, 'text', '') or ''
            parsed = parse_gemini_analysis(text)
            if parsed:
                return parsed
        except Exception as exc:
            logger.exception('Gemini mental health analysis failed: %s', exc)

    return fallback_mental_health_analysis(condition, answers)




@login_required(login_url='login')
def fallback_mental_health_analysis(condition, answers):
    return {
        'analysis': (
            'Thank you for completing this check-in. The experiences you described may be affecting your day-to-day life. '
            'This screening is not a diagnosis, but it can highlight patterns worth discussing in the context of {}.'
        ).format(condition),
        'next_steps': [
            'Share these results with a qualified healthcare provider or mental health professional for an accurate diagnosis and personalized advice.',
            'Talk to a trusted friend, family member, or mentor about what you are experiencing.',
            'Review reputable mental health resources such as NAMI, Mind, or the National Institute of Mental Health for trusted guidance.',
            'Track your mood, sleep, and energy in a short journal to notice patterns over time.',
        ],
    }


MENTAL_HEALTH_QUESTIONNAIRE = {
    'questionnaire': 'Comprehensive Mental Health Intake',
    'version': '1.0',
    'disclaimer': 'This tool is a self-report screener, not a diagnostic instrument. It does not diagnose any condition.',
    'start_node': 'q_initial_selection',
    'crisis_resources': {'us': {'call_or_text': '988', 'name': '988 Suicide & Crisis Lifeline', 'text_line': 'Text HOME to 741741 (Crisis Text Line)'}, 'international_note': 'Contact your local emergency number or visit findahelpline.com.'},
    'nodes': {
        'q_initial_selection': {'id': 'q_initial_selection', 'text': 'Which of the following best describes your primary concern right now?', 'type': 'single_choice', 'options': [{'label': 'Stress', 'next_node': 'stress_q1'}, {'label': 'Anxiety', 'next_node': 'anx_q1'}, {'label': 'Depression / low mood', 'next_node': 'dep_q1'}, {'label': 'Burnout', 'next_node': 'burn_q1'}, {'label': 'Sleep difficulties', 'next_node': 'sleep_q1'}]},
        'stress_q1': {'id': 'stress_q1', 'text': 'How often do you feel overwhelmed by everyday responsibilities?', 'type': 'single_choice', 'options': [{'label': 'Rarely', 'next_node': 'stress_q2_mild'}, {'label': 'Sometimes', 'next_node': 'stress_q2_moderate'}, {'label': 'Often or always', 'next_node': 'stress_q2_severe'}]},
        'stress_q2_mild': {'id': 'stress_q2_mild', 'text': 'Do you feel you have effective ways to decompress after a busy day?', 'type': 'single_choice', 'options': [{'label': 'Yes, usually', 'next_node': 'safety_check'}, {'label': 'No, I struggle to relax', 'next_node': 'safety_check'}]},
        'stress_q2_moderate': {'id': 'stress_q2_moderate', 'text': 'Do these feelings come and go, or are they fairly constant?', 'type': 'single_choice', 'options': [{'label': 'Come and go', 'next_node': 'safety_check'}, {'label': 'Fairly constant', 'next_node': 'safety_check'}]},
        'stress_q2_severe': {'id': 'stress_q2_severe', 'text': 'Are you noticing physical symptoms like a racing heart, headaches, or muscle tension?', 'type': 'single_choice', 'options': [{'label': 'Yes, frequently', 'next_node': 'safety_check'}, {'label': 'No, mostly emotional', 'next_node': 'safety_check'}]},
        'anx_q1': {'id': 'anx_q1', 'text': 'How often do you feel tense, restless, or on edge?', 'type': 'single_choice', 'options': [{'label': 'Rarely', 'next_node': 'safety_check'}, {'label': 'Several days', 'next_node': 'safety_check'}, {'label': 'More than half the days', 'next_node': 'safety_check'}]},
        'dep_q1': {'id': 'dep_q1', 'text': 'How often have you felt down, depressed, or hopeless over the last two weeks?', 'type': 'single_choice', 'options': [{'label': 'Not at all', 'next_node': 'safety_check'}, {'label': 'Several days', 'next_node': 'safety_check'}, {'label': 'More than half the days', 'next_node': 'safety_check'}, {'label': 'Nearly every day', 'next_node': 'safety_check'}]},
        'burn_q1': {'id': 'burn_q1', 'text': 'How often do you feel emotionally drained by your work or main daily role?', 'type': 'single_choice', 'options': [{'label': 'Never', 'next_node': 'safety_check'}, {'label': 'Sometimes', 'next_node': 'safety_check'}, {'label': 'Often or daily', 'next_node': 'safety_check'}]},
        'sleep_q1': {'id': 'sleep_q1', 'text': 'What sleep difficulty are you experiencing most?', 'type': 'single_choice', 'options': [{'label': 'Trouble falling asleep', 'next_node': 'safety_check'}, {'label': 'Waking during the night', 'next_node': 'safety_check'}, {'label': 'Waking too early', 'next_node': 'safety_check'}, {'label': 'Sleeping too much', 'next_node': 'safety_check'}]},
        'safety_check': {'id': 'safety_check', 'text': "Before we continue: in the past two weeks, have you had any thoughts of harming yourself or that life isn't worth living?", 'type': 'single_choice', 'options': [{'label': 'No', 'next_node': 'check_in_complete'}, {'label': 'Yes', 'next_node': 'crisis_intervention'}]},
        'crisis_intervention': {'id': 'crisis_intervention', 'type': 'endpoint_alert', 'text': 'Your safety matters most. Please call or text 988, text HOME to 741741, or call your local emergency number if you are in immediate danger.', 'action': 'trigger_safety_protocol', 'blocking': True},
        'check_in_complete': {'id': 'check_in_complete', 'type': 'endpoint', 'text': 'Thanks for completing this check-in. Your responses are ready to review.', 'options': []},
    },
}


def _get_questionnaire_node(node_id):
    return MENTAL_HEALTH_QUESTIONNAIRE['nodes'].get(node_id, MENTAL_HEALTH_QUESTIONNAIRE['nodes']['q_initial_selection'])


def _resolve_questionnaire_transition(node, selected_option, state):
    for option in node.get('options', []):
        if option.get('label') == selected_option:
            return option.get('next_node') or state.get('current_node')
    return state.get('current_node', MENTAL_HEALTH_QUESTIONNAIRE['start_node'])


def parse_gemini_analysis(text):
    if not text:
        return None
    try:
        payload = json.loads(text.strip().replace('```json', '').replace('```', '').strip())
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or not payload.get('analysis'):
        return None
    return {'analysis': payload['analysis'], 'next_steps': payload.get('next_steps') or fallback_mental_health_analysis('your selected condition', {}).get('next_steps')}


def generate_mental_health_analysis(condition, answers):
    return fallback_mental_health_analysis(condition, answers)


def dashboard(request):
    ensure_medicalreport_schema()
    try:
        reports = MedicalReport.objects.filter(user=request.user).order_by('-uploaded_at')[:3]
    except Exception:
        reports = []
    # Compute simple stats
    index_points = BrainHealthDataIndex.objects.count()
    clinicians_count = Clinician.objects.filter(available_for_telemedicine=True).count()
    facilities_count = MedicalTourismFacility.objects.count()

    # Prepare last 7 days cognitive metrics for this user
    today = timezone.now().date()
    labels = []
    focus_series = []
    stress_series = []
    for i in range(6, -1, -1):
        d = today - timezone.timedelta(days=i)
        labels.append(d.strftime('%a'))
        cm = CognitiveMetric.objects.filter(user=request.user, date=d).first()
        if cm:
            focus_series.append(cm.focus_retention)
            stress_series.append(cm.stress_level)
        else:
            focus_series.append(0)
            stress_series.append(0)

    # Node events (most recent 6)
    node_events = NodeEvent.objects.order_by('-timestamp')[:6]

    # indices JSON for map
    indices = BrainHealthDataIndex.objects.all()
    indices_json = []
    for idx in indices:
        indices_json.append({
            'lat': idx.latitude,
            'lng': idx.longitude,
            'region': idx.region_name,
            'overall': idx.overall_index,
            'socio': idx.socioeconomic_score,
            'env': idx.environmental_impact_score
        })
    indices_json = json.dumps(indices_json)

    # index points change: compare counts in last 30 days vs previous 30 days
    days_30 = timezone.now() - timezone.timedelta(days=30)
    days_60 = timezone.now() - timezone.timedelta(days=60)
    recent_count = BrainHealthDataIndex.objects.filter(last_updated__gte=days_30).count()
    prev_count = BrainHealthDataIndex.objects.filter(last_updated__gte=days_60, last_updated__lt=days_30).count()
    index_points_change = '+0%'
    try:
        if prev_count == 0:
            index_points_change = '+0%'
        else:
            pct = int(((recent_count - prev_count) / prev_count) * 100)
            index_points_change = f"{pct:+d}%"
    except Exception:
        index_points_change = '+0%'

    dashboard_hints = get_unseen_feature_hints(request, ['dashboard_overview', 'dashboard_chart', 'dashboard_reports'])

    return render(request, 'dashboard.html', {
        'index_points': index_points,
        'clinicians_count': clinicians_count,
        'facilities_count': facilities_count,
        'profile': get_current_profile(request),
        'reports': reports,
        'wallet_balance': HealthWalletTransaction.objects.filter(user=request.user).aggregate(total=models.Sum('amount'))['total'] or 0,
        'chart_labels': labels,
        'focus_series': focus_series,
        'stress_series': stress_series,
        'node_events': node_events,
        'indices_json': indices_json,
        'chart_labels': labels,
        'focus_series': focus_series,
        'stress_series': stress_series,
        'index_points_change': index_points_change,
        'feature_hints': dashboard_hints,
    })

@login_required(login_url='login')
def onboarding(request):
    if request.method == "POST":
        profile_values = {
            'full_name': request.POST.get('full_name', request.user.get_full_name() or request.user.username),
            'pathway': request.POST.get('pathway', 'Patient/User'),
            'cognitive_goal': request.POST.get('cognitive_goal', 'Memory & Concentration'),
            'bci_familiarity': request.POST.get('bci_familiarity', 'First Time'),
            'environment': request.POST.get('environment', 'Urban Center'),
            'subscription_tier': request.POST.get('subscription_tier', 'Standard Pro'),
            'web3_wallet': request.POST.get('web3_wallet', ''),
            'data_processing_consent': request.POST.get('consent') == 'on'
        }
        NeuroProfile.objects.update_or_create(user=request.user, defaults=profile_values)
        return redirect('dashboard')
    return render(request, 'onboarding.html')

@login_required(login_url='login')
def myspace(request):
    profile = get_current_profile(request)
    reports = MedicalReport.objects.filter(user=request.user)
    enrollments = Enrollment.objects.filter(user=request.user)
    protocols = WellnessProtocol.objects.filter(user=request.user)
    wallet_total = HealthWalletTransaction.objects.filter(user=request.user).aggregate(total=models.Sum('amount'))['total'] or 0

    coverage_parts = [
        bool(profile),
        bool(profile and profile.full_name),
        bool(profile and profile.web3_wallet),
        reports.exists(),
        enrollments.exists(),
        protocols.exists(),
        bool(wallet_total),
    ]
    coverage_pct = f"{(sum(coverage_parts) / len(coverage_parts)) * 100:.1f}%"

    records_count = reports.count()
    bench_active = enrollments.count() + protocols.count()
    fund_total = f"${wallet_total:,.2f}" if wallet_total else '$0.00'

    node_events = NodeEvent.objects.order_by('-timestamp')[:12]
    indices = BrainHealthDataIndex.objects.all()
    indices_data = []
    for i in indices:
        indices_data.append({
            'lat': i.latitude,
            'lng': i.longitude,
            'region': i.region_name,
            'overall': i.overall_index,
            'socio': i.socioeconomic_score,
            'env': i.environmental_impact_score
        })
    indices_json = json.dumps(indices_data)

    myspace_hints = get_unseen_feature_hints(request, ['myspace_overview', 'myspace_map', 'myspace_telemetry'])

    return render(request, 'myspace.html', {
        'indices_json': indices_json,
        'coverage_pct': coverage_pct,
        'records_count': records_count,
        'bench_active': bench_active,
        'fund_total': fund_total,
        'node_events': node_events,
        'feature_hints': myspace_hints,
    })

@login_required(login_url='login')
def clinical_care(request):
    ensure_medicalreport_schema()
    if request.method == "POST":
        title = request.POST.get('title', '').strip()
        doc_type = request.POST.get('document_type', 'EEG Diagnostic Report')
        doc_file = request.FILES.get('document_file')
        
        if title:
            file_size_str = None
            if doc_file:
                hasher = hashlib.sha256()
                for chunk in doc_file.chunks():
                    hasher.update(chunk)
                enc_hash = f"0x{hasher.hexdigest()[:24]}"
                
                size_bytes = doc_file.size
                if size_bytes >= 1024 * 1024:
                    file_size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    file_size_str = f"{max(1, int(size_bytes / 1024))} KB"
            else:
                enc_hash = f"0x{uuid.uuid4().hex[:24]}"

            MedicalReport.objects.create(
                user=request.user,
                title=title,
                document_type=doc_type,
                file=doc_file,
                file_size=file_size_str,
                encrypted_hash=enc_hash
            )
            django_messages.success(request, f"Medical Report '{title}' successfully uploaded and SHA-256 anchored to e-MR registry.")
            return redirect('clinical_care')
        else:
            django_messages.error(request, "Please enter a valid report title.")

    clinicians = Clinician.objects.all()
    if not clinicians.exists():
        docs = [
            ("Dr. Aris Thorne", "Neurosurgery & BCI", "Geneva Neurological", 4.95, "https://ui-avatars.com/api/?name=Aris+Thorne&background=1e293b&color=3b82f6"),
            ("Dr. Chukwuma Adebayo", "Cognitive Neurology", "Neural Village Labs", 4.92, "https://ui-avatars.com/api/?name=Chukwuma+Adebayo&background=1e293b&color=10b981"),
            ("Dr. Elena Rostova", "EEG Pathology", "Harvard Brain Science", 4.88, "https://ui-avatars.com/api/?name=Elena+Rostova&background=1e293b&color=8b5cf6"),
            ("Dr. Satoshi Nakamoto", "Neuro-Encryption", "Tokyo Tech", 4.99, "https://ui-avatars.com/api/?name=Satoshi+N&background=1e293b&color=f59e0b"),
            ("Dr. Sarah Jenkins", "Pediatric Neurology", "London Health", 4.75, "https://ui-avatars.com/api/?name=Sarah+Jenkins&background=1e293b&color=ef4444"),
        ]
        for name, spec, inst, rat, img in docs:
            Clinician.objects.create(name=name, specialty=spec, institution=inst, rating=rat, image_url=img)
        clinicians = Clinician.objects.all()

    try:
        reports = list(MedicalReport.objects.filter(user=request.user).order_by('-uploaded_at'))
    except Exception:
        reports = []

    return render(request, 'clinical_care.html', {
        'clinicians': clinicians, 
        'reports': reports,
        'profile': get_current_profile(request)
    })

@login_required(login_url='login')
def medical_tourism(request):
    facilities = MedicalTourismFacility.objects.all()
    facility_data = [{'id': f.id, 'name': f.name, 'type': f.get_facility_type_display(), 'country': f.country, 'city': f.city, 'lat': f.latitude, 'lng': f.longitude, 'desc': f.description} for f in facilities]
    return render(request, 'medical_tourism.html', {
        'facilities_json': facility_data, 
        'facilities': facilities,
        'itineraries': MedicalItinerary.objects.filter(user=request.user),
        'profile': get_current_profile(request)
    })


@login_required(login_url='login')
def medical_itinerary_create(request):
    if request.method != 'POST':
        return redirect('medical_tourism')

    facility_id = request.POST.get('facility')
    scheduled_date = request.POST.get('date')
    duration = request.POST.get('duration')
    notes = request.POST.get('notes', '')

    try:
        facility = MedicalTourismFacility.objects.get(id=int(facility_id))
    except (MedicalTourismFacility.DoesNotExist, ValueError, TypeError):
        django_messages.error(request, 'Selected facility not found.')
        return redirect('medical_tourism')

    try:
        dur = int(duration) if duration else None
    except ValueError:
        dur = None

    try:
        itin = MedicalItinerary.objects.create(
            destination_facility=facility,
            scheduled_date=scheduled_date,
            duration_days=dur,
            notes=notes,
            user=request.user,
            status='Planned'
        )
        django_messages.success(request, 'Itinerary created.')
    except Exception as e:
        django_messages.error(request, f'Error creating itinerary: {e}')

    return redirect('medical_tourism')

@login_required(login_url='login')
def insurance(request):
    plans = InsurancePlan.objects.filter(is_active=True)
    user_sub = None
    if request.user.is_authenticated:
        user_sub = UserInsuranceSubscription.objects.filter(user=request.user).order_by('-started_at').first()
    return render(request, 'insurance.html', {'plans': plans, 'profile': get_current_profile(request), 'user_subscription': user_sub})


@login_required(login_url='login')
def insurance_subscribe(request):
    if request.method != 'POST':
        return redirect('insurance')

    plan_id = request.POST.get('plan_id')
    try:
        plan = InsurancePlan.objects.get(id=int(plan_id))
    except (InsurancePlan.DoesNotExist, ValueError, TypeError):
        django_messages.error(request, 'Selected plan not found.')
        return redirect('insurance')

    profile = get_current_profile(request)
    sub = UserInsuranceSubscription.objects.create(
        user=request.user,
        profile=profile,
        plan=plan,
        status='active',
        discount_pct=0,
        underwriting_score=None,
        last_synced=timezone.now()
    )
    django_messages.success(request, f'Subscribed to {plan.name}.')
    return redirect('insurance')

@login_required(login_url='login')
def appointment(request):
    if request.method == 'POST':
        clinician_id = request.POST.get('clinician')
        date = request.POST.get('date')
        time = request.POST.get('time')
        modality = request.POST.get('appt_type')
        notes = request.POST.get('notes', '')
        sync_baseline = bool(request.POST.get('sync_baseline'))
        sync_emr = bool(request.POST.get('sync_emr'))
        sync_pharm = bool(request.POST.get('sync_pharm'))

        clinician = None
        if clinician_id:
            try:
                clinician = Clinician.objects.get(id=int(clinician_id))
            except (Clinician.DoesNotExist, ValueError):
                clinician = None

        # create appointment
        from .models import Appointment, DataAccessGrant
        appt = Appointment.objects.create(
            user=request.user,
            clinician=clinician,
            scheduled_date=date,
            scheduled_time=time,
            modality=modality or 'telemedicine',
            notes=notes,
            sync_baseline=sync_baseline,
            sync_emr=sync_emr,
            sync_pharm=sync_pharm,
            fee=0
        )

        # create grants records (not implemented blockchain)
        if sync_baseline:
            DataAccessGrant.objects.create(appointment=appt, grant_type='baseline', granted=True)
        if sync_emr:
            DataAccessGrant.objects.create(appointment=appt, grant_type='emr', granted=True)
        if sync_pharm:
            DataAccessGrant.objects.create(appointment=appt, grant_type='pharm', granted=True)

        django_messages.success(request, 'Appointment requested.')
        return redirect('history')

    return render(request, 'appointment.html', {'clinicians': Clinician.objects.all(), 'profile': get_current_profile(request)})

@login_required(login_url='login')
def messages(request):
    # list conversations the user participates in
    conversations = Conversation.objects.filter(participants=request.user).order_by('-last_activity')
    active_conv = None
    conv_id = request.GET.get('c')
    if conv_id:
        try:
            active_conv = Conversation.objects.get(id=int(conv_id))
        except (Conversation.DoesNotExist, ValueError, TypeError):
            active_conv = None

    # if no conversations, optionally build from direct messages where user is recipient or sender_user
    if not conversations.exists():
        # build lightweight conv list from existing messages
        msgs = Message.objects.filter(models.Q(recipient=request.user) | models.Q(sender_user=request.user)).order_by('-timestamp')
        conversations = []
        # leave as empty list for template to show empty state

    return render(request, 'messages.html', {'conversations': conversations, 'active_conversation': active_conv, 'profile': get_current_profile(request)})


@login_required(login_url='login')
def messages_send(request):
    if request.method != 'POST':
        return redirect('messages')

    conv_id = request.POST.get('conversation_id')
    recipient_id = request.POST.get('recipient_id')
    content = request.POST.get('content', '').strip()

    if not content:
        django_messages.error(request, 'Message content cannot be empty.')
        return redirect('messages')

    conv = None
    if conv_id:
        try:
            conv = Conversation.objects.get(id=int(conv_id))
        except (Conversation.DoesNotExist, ValueError, TypeError):
            conv = None

    # if no conversation, try to create one for recipient
    if not conv and recipient_id:
        try:
            recip = User.objects.get(id=int(recipient_id))
        except (User.DoesNotExist, ValueError, TypeError):
            recip = None
        if recip:
            conv = Conversation.objects.create()
            conv.participants.add(request.user, recip)

    if not conv:
        django_messages.error(request, 'Unable to send message (no conversation or recipient).')
        return redirect('messages')

    msg = Message.objects.create(
        sender=request.user.username,
        sender_user=request.user,
        recipient=recip if 'recip' in locals() else None,
        conversation=conv,
        content=content
    )
    django_messages.success(request, 'Message sent.')
    from django.urls import reverse
    return redirect(reverse('messages') + f'?c={conv.id}')

@login_required(login_url='login')
def health_wallet(request):
    txs = HealthWalletTransaction.objects.filter(user=request.user).order_by('-date')
    balance = txs.aggregate(total=models.Sum('amount'))['total'] or 0
    # telemetry/yield placeholders removed — leave template to show simple values
    return render(request, 'health_wallet.html', {'transactions': txs, 'profile': get_current_profile(request), 'wallet_balance': balance})

@login_required(login_url='login')
def history(request):
    reports = MedicalReport.objects.filter(user=request.user).order_by('-uploaded_at')
    return render(request, 'history.html', {'reports': reports, 'profile': get_current_profile(request)})

@login_required(login_url='login')
def history_report_detail(request, report_id):
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    return render(request, 'history_report_detail.html', {'report': report, 'profile': get_current_profile(request)})

@login_required(login_url='login')
def history_download_report(request, report_id):
    if request.method != 'POST':
        return redirect('history')
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    content = (
        f"Medical Report: {report.title}\n"
        f"Type: {report.document_type}\n"
        f"Uploaded: {report.uploaded_at.isoformat()}\n"
        f"Encrypted Hash: {report.encrypted_hash}\n\n"
        "This is a placeholder export for the selected medical report."
    )
    response = HttpResponse(content, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="medical-report-{report.id}.txt"'
    return response

@login_required(login_url='login')
def history_share_report(request, report_id):
    if request.method != 'POST':
        return redirect('history')
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    django_messages.success(request, f'Report "{report.title}" shared successfully.')
    return redirect('history')

@login_required(login_url='login')
def nbhdi_resources(request):
    resources = ResourceItem.objects.all()
    return render(request, 'nbhdi_resources.html', {'profile': get_current_profile(request), 'resources': resources})

@login_required(login_url='login')
def nbhdi_resource_action(request, resource_id):
    resource = get_object_or_404(ResourceItem, id=resource_id)
    if resource.link:
        return redirect(resource.link)
    django_messages.info(request, 'This resource is not currently available for download.')
    return redirect('nbhdi_resources')

@login_required(login_url='login')
def wellness(request):
    protocol = WellnessProtocol.objects.filter(user=request.user).order_by('-created_at').first()
    return render(request, 'wellness.html', {'profile': get_current_profile(request), 'protocol': protocol})

@login_required(login_url='login')
def wellness_sync(request):
    if request.method != 'POST':
        return redirect('wellness')
    protocol, created = WellnessProtocol.objects.get_or_create(
        user=request.user,
        defaults={
            'title': 'Neural Village Biomarker Sync',
            'biomarker_source': 'Neural Village Device',
            'status': 'synced',
            'last_synced': timezone.now()
        }
    )
    if not created:
        protocol.status = 'synced'
        protocol.last_synced = timezone.now()
        protocol.save()
    django_messages.success(request, 'Hardware sync complete. Wellness protocol updated.')
    return redirect('wellness')

@login_required(login_url='login')
def neurolearn(request):
    courses = NeurolearnCourse.objects.all()
    enrollments = Enrollment.objects.filter(user=request.user)
    enrolled_course_ids = set(enrollment.course_id for enrollment in enrollments)
    return render(request, 'neurolearn.html', {
        'courses': courses,
        'profile': get_current_profile(request),
        'enrollments': {enrollment.course_id: enrollment for enrollment in enrollments},
        'enrolled_course_ids': enrolled_course_ids
    })

@login_required(login_url='login')
def neurolearn_start_module(request, course_id):
    if request.method != 'POST':
        return redirect('neurolearn')
    course = get_object_or_404(NeurolearnCourse, id=course_id)
    enrollment, created = Enrollment.objects.get_or_create(
        user=request.user,
        course=course,
        defaults={'status': 'in_progress', 'progress_pct': 0}
    )
    if not created:
        django_messages.info(request, 'You already started this course.')
    else:
        django_messages.success(request, f'You have started "{course.title}".')
    return redirect('neurolearn')

@login_required(login_url='login')
def greenspace(request):
    membership = GreenSpaceMembership.objects.filter(user=request.user).first()
    return render(request, 'greenspace.html', {'profile': get_current_profile(request), 'membership': membership})

@login_required(login_url='login')
def greenspace_join(request):
    if request.method != 'POST':
        return redirect('greenspace')
    membership, created = GreenSpaceMembership.objects.get_or_create(user=request.user)
    if created:
        django_messages.success(request, 'Welcome to the Nourish DAO!')
    else:
        django_messages.info(request, 'You are already a member of the Nourish DAO.')
    return redirect('greenspace')

@login_required(login_url='login')
def profile_lock(request):
    profile = get_current_profile(request)
    if profile:
        profile.account_locked = True
        profile.save()
        request.user.is_active = False
        request.user.save()
        django_messages.success(request, 'Account locked. You will need administrator access to reactivate this account.')
    else:
        django_messages.error(request, 'Unable to lock account because your profile could not be found.')
    return redirect('profile')

@login_required(login_url='login')
def profile(request):
    return render(request, 'profile.html', {'profile': get_current_profile(request)})


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def signup(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        if not username or not password:
            django_messages.error(request, 'Username and password are required.')
            return redirect('signup')
        if User.objects.filter(username=username).exists():
            django_messages.error(request, 'Username is already taken.')
            return redirect('signup')
        user = User.objects.create_user(username=username, email=email, password=password)
        user.save()
        login(request, user)
        django_messages.success(request, f'Welcome to NeuralSpace, {user.username}! Your account was created successfully.')
        return redirect('onboarding')
    return render(request, 'signup.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            django_messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            django_messages.error(request, 'Invalid username or password. Please try again.')
            return redirect('login')
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    django_messages.info(request, 'You have been signed out safely.')
    return redirect('landing')


# Keep the route implementation at module scope; older generated blocks above are nested in another view.
MENTAL_HEALTH_QUESTIONNAIRE = {
    'questionnaire': 'Comprehensive Mental Health Intake',
    'version': '1.0',
    'disclaimer': 'This tool is a self-report screener, not a diagnostic instrument. It does not diagnose any condition.',
    'start_node': 'q_initial_selection',
    'crisis_resources': {
        'us': {
            'call_or_text': '988',
            'name': '988 Suicide & Crisis Lifeline',
            'text_line': 'Text HOME to 741741 (Crisis Text Line)',
        },
        'international_note': 'If outside the US, direct users to their local emergency number or findahelpline.com',
    },
    'nodes': {
        'q_initial_selection': {'id': 'q_initial_selection', 'text': 'Which of the following best describes your primary concern right now?', 'type': 'single_choice', 'options': [{'label': 'Stress', 'next_node': 'stress_q1'}, {'label': 'Anxiety', 'next_node': 'anx_q1'}, {'label': 'Depression / low mood', 'next_node': 'dep_q1'}, {'label': 'Burnout', 'next_node': 'burn_q1'}, {'label': 'Sleep difficulties', 'next_node': 'sleep_q1'}]},
        'stress_q1': {'id': 'stress_q1', 'text': 'How often do you feel overwhelmed by everyday responsibilities?', 'type': 'single_choice', 'options': [{'label': 'Rarely', 'next_node': 'stress_q2_mild'}, {'label': 'Sometimes', 'next_node': 'stress_q2_moderate'}, {'label': 'Often', 'next_node': 'stress_q2_severe'}, {'label': 'Often or always', 'next_node': 'stress_q2_severe'}]},
        'stress_q2_severe': {'id': 'stress_q2_severe', 'text': 'When responsibilities pile up, what gets hardest?', 'type': 'single_choice', 'options': [{'label': 'Making decisions', 'next_node': 'stress_q3_control'}, {'label': 'Focusing', 'next_node': 'stress_q3_control'}, {'label': 'Relaxing', 'next_node': 'stress_q3_control'}, {'label': 'Keeping up with plans', 'next_node': 'stress_q3_control'}]},
        'stress_q2_mild': {'id': 'stress_q2_mild', 'text': 'What usually helps you feel more regulated?', 'type': 'single_choice', 'options': [{'label': 'Boundaries', 'next_node': 'safety_check'}, {'label': 'Recovery time', 'next_node': 'safety_check'}]},
        'stress_q2_moderate': {'id': 'stress_q2_moderate', 'text': 'What usually helps you feel more regulated?', 'type': 'single_choice', 'options': [{'label': 'Boundaries', 'next_node': 'safety_check'}, {'label': 'Support from others', 'next_node': 'safety_check'}]},
        'stress_q3_control': {'id': 'stress_q3_control', 'text': 'What usually helps you feel more regulated?', 'type': 'single_choice', 'options': [{'label': 'Boundaries', 'next_node': 'safety_check'}, {'label': 'Recovery time', 'next_node': 'safety_check'}, {'label': 'Reduced workload', 'next_node': 'safety_check'}, {'label': 'Support from others', 'next_node': 'safety_check'}]},
        'anx_q1': {'id': 'anx_q1', 'text': 'How often do you feel tense, restless, or on edge?', 'type': 'single_choice', 'options': [{'label': 'Rarely', 'next_node': 'safety_check'}, {'label': 'Several days', 'next_node': 'safety_check'}]},
        'dep_q1': {'id': 'dep_q1', 'text': 'How often have you felt down, depressed, or hopeless over the last two weeks?', 'type': 'single_choice', 'options': [{'label': 'Not at all', 'next_node': 'safety_check'}, {'label': 'Several days', 'next_node': 'safety_check'}]},
        'burn_q1': {'id': 'burn_q1', 'text': 'How often do you feel emotionally drained by your work or main daily role?', 'type': 'single_choice', 'options': [{'label': 'Never', 'next_node': 'safety_check'}, {'label': 'Sometimes', 'next_node': 'safety_check'}]},
        'sleep_q1': {'id': 'sleep_q1', 'text': 'What sleep difficulty are you experiencing most?', 'type': 'single_choice', 'options': [{'label': 'Trouble falling asleep', 'next_node': 'safety_check'}, {'label': 'Waking during the night', 'next_node': 'safety_check'}]},
        'safety_check': {'id': 'safety_check', 'text': "Before we continue: in the past two weeks, have you had any thoughts of harming yourself or that life isn't worth living?", 'type': 'single_choice', 'options': [{'label': 'No', 'next_node': 'check_in_complete'}, {'label': 'Yes', 'next_node': 'crisis_intervention'}]},
        'crisis_intervention': {'id': 'crisis_intervention', 'type': 'endpoint_alert', 'text': 'Your safety matters most. Please call or text 988, text HOME to 741741, or call your local emergency number if you are in immediate danger.', 'blocking': True},
        'check_in_complete': {'id': 'check_in_complete', 'type': 'endpoint', 'text': 'Thanks for completing this check-in. Your responses are ready to review.', 'options': []},
    },
}


def fallback_mental_health_analysis(condition, answers):
    return {
        'analysis': 'This screening is not a diagnosis, but it can highlight patterns worth discussing in the context of {}.'.format(condition),
        'next_steps': ['Share these results with a qualified healthcare provider or mental health professional for an accurate diagnosis and personalized advice.'],
    }


def generate_mental_health_analysis(condition, answers):
    return fallback_mental_health_analysis(condition, answers)


def _get_questionnaire_node(node_id):
    return MENTAL_HEALTH_QUESTIONNAIRE['nodes'].get(node_id, MENTAL_HEALTH_QUESTIONNAIRE['nodes']['q_initial_selection'])


def _resolve_questionnaire_transition(node, selected_option, state):
    for option in node.get('options', []):
        if option.get('label') == selected_option:
            return option.get('next_node', state.get('current_node'))
    return state.get('current_node', MENTAL_HEALTH_QUESTIONNAIRE['start_node'])


@login_required(login_url='login')
def mental_health_screening(request):
    conditions = ['Stress', 'Anxiety', 'Depression', 'Burnout', 'Sleep difficulties']
    default_answers = {'q1': 'Sometimes', 'q2': 'Rarely', 'q3': 'Occasionally', 'q4': 'Sometimes', 'q5': 'Rarely'}

    if request.method == 'POST' and request.POST.get('restart_assessment'):
        request.session['mental_health_questionnaire'] = {
            'current_node': MENTAL_HEALTH_QUESTIONNAIRE['start_node'],
            'responses': {},
            'return_to_node': None,
        }

    legacy_keys = [key for key in request.POST.keys() if key.startswith('q')]
    if request.method == 'POST' and legacy_keys and not request.POST.get('current_node') and not request.POST.get('selected_option'):
        condition = request.POST.get('condition', 'Stress').strip() or 'Stress'
        answers = {key: request.POST.get(key, default_answers.get(key, '')) for key in default_answers}
        questions = [
            {'id': 'q1', 'text': 'How often do you feel overwhelmed by everyday responsibilities?', 'options': ['Rarely', 'Sometimes', 'Often', 'Almost always'], 'selected': answers.get('q1', default_answers['q1'])},
            {'id': 'q2', 'text': 'When responsibilities pile up, what gets hardest?', 'options': ['Making decisions', 'Focusing', 'Relaxing', 'Keeping up with plans'], 'selected': answers.get('q2', default_answers['q2'])},
            {'id': 'q3', 'text': 'What usually helps you feel more regulated?', 'options': ['Boundaries', 'Recovery time', 'Reduced workload', 'Support from others'], 'selected': answers.get('q3', default_answers['q3'])},
        ]
        analysis = generate_mental_health_analysis(condition, answers)
        return render(request, 'mental_health.html', {
            'profile': get_current_profile(request),
            'conditions': conditions,
            'condition': condition,
            'answers': answers,
            'questions': questions,
            'analysis': analysis,
            'submitted': True,
            'question_node': None,
            'questionnaire': MENTAL_HEALTH_QUESTIONNAIRE,
        })

    state = request.session.setdefault('mental_health_questionnaire', {
        'current_node': MENTAL_HEALTH_QUESTIONNAIRE['start_node'],
        'responses': {},
        'return_to_node': None,
    })

    if request.method == 'POST' and request.POST.get('restart_assessment'):
        reset_state = {
            'current_node': MENTAL_HEALTH_QUESTIONNAIRE['start_node'],
            'responses': {},
            'return_to_node': None,
            'condition': request.POST.get('condition', 'Stress').strip() or 'Stress',
        }
        request.session['mental_health_questionnaire'] = reset_state
        state = reset_state
        return render(request, 'mental_health.html', {
            'profile': get_current_profile(request),
            'conditions': conditions,
            'condition': state.get('condition', 'Stress'),
            'answers': default_answers,
            'analysis': None,
            'submitted': False,
            'question_node': _get_questionnaire_node(MENTAL_HEALTH_QUESTIONNAIRE['start_node']),
            'questionnaire': MENTAL_HEALTH_QUESTIONNAIRE,
            'responses': {},
            'current_node': MENTAL_HEALTH_QUESTIONNAIRE['start_node'],
        })

    if request.method == 'GET' and state.get('current_node') in {'check_in_complete', 'crisis_intervention'}:
        reset_state = {
            'current_node': MENTAL_HEALTH_QUESTIONNAIRE['start_node'],
            'responses': {},
            'return_to_node': None,
            'condition': 'Stress',
        }
        request.session['mental_health_questionnaire'] = reset_state
        state = reset_state

    if request.method == 'POST' and (request.POST.get('current_node') or request.POST.get('selected_option')):
        state['condition'] = request.POST.get('condition', state.get('condition', 'Stress')).strip() or 'Stress'
        current_node_id = request.POST.get('current_node') or MENTAL_HEALTH_QUESTIONNAIRE['start_node']
        current_node = _get_questionnaire_node(current_node_id)
        selected_option = request.POST.get('selected_option') or request.POST.get('answer') or request.POST.get('value')
        if selected_option:
            state['responses'][current_node_id] = selected_option
            state['return_to_node'] = current_node_id
            state['current_node'] = _resolve_questionnaire_transition(current_node, selected_option, state)
            request.session['mental_health_questionnaire'] = state

    current_node_id = state.get('current_node', MENTAL_HEALTH_QUESTIONNAIRE['start_node'])
    if current_node_id in {'check_in_complete', 'crisis_intervention'}:
        condition = state.get('condition') or 'Stress'
        answers = {key: value for key, value in state.get('responses', {}).items()}
        return render(request, 'mental_health.html', {
            'profile': get_current_profile(request),
            'conditions': conditions,
            'condition': condition,
            'answers': answers,
            'questions': [],
            'analysis': generate_mental_health_analysis(condition, answers),
            'submitted': True,
            'question_node': None,
            'questionnaire': MENTAL_HEALTH_QUESTIONNAIRE,
        })

    question_node = _get_questionnaire_node(current_node_id)
    return render(request, 'mental_health.html', {
        'profile': get_current_profile(request),
        'conditions': conditions,
        'condition': state.get('condition', 'Stress'),
        'answers': default_answers,
        'analysis': None,
        'submitted': False,
        'question_node': question_node,
        'questionnaire': MENTAL_HEALTH_QUESTIONNAIRE,
        'responses': state.get('responses', {}),
        'current_node': current_node_id,
    })
