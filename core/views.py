from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .models import *
from django.db import models
import json

def get_current_profile(request=None):
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        return NeuroProfile.objects.filter(user=request.user).first()
    return None

@login_required(login_url='login')
def dashboard(request):
    reports = MedicalReport.objects.filter(user=request.user).order_by('-uploaded_at')[:3]
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
        'index_points_change': index_points_change
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
    # aggregate some simple stats for the MySpace dashboard
    coverage_pct = '94.2%'
    records_count = MedicalReport.objects.count()
    bench_active = 3
    fund_total = '$42.8k'

    # fetch recent node events
    node_events = NodeEvent.objects.order_by('-timestamp')[:12]
    # build indices array for map
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

    return render(request, 'myspace.html', {
        'indices_json': indices_json,
        'coverage_pct': coverage_pct,
        'records_count': records_count,
        'bench_active': bench_active,
        'fund_total': fund_total,
        'node_events': node_events
    })

@login_required(login_url='login')
def clinical_care(request):
    return render(request, 'clinical_care.html', {
        'clinicians': Clinician.objects.all(), 
        'reports': MedicalReport.objects.filter(user=request.user),
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
