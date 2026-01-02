from django.shortcuts import render
import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, TemplateView
from .models import Course, TimeSlot, Booking
from .forms import CourseForm, TimeSlotForm, TimeSlotFormSet
from datetime import timedelta
from django.contrib import messages
from django.views import View
from datetime import datetime
import ast
from django.core.mail import send_mail

stripe.api_key = settings.STRIPE_SECRET_KEY 



class CourseListView(ListView):
    model = Course
    template_name = 'courses/course_list.html'
    context_object_name = 'courses'

class MyCourseListView(LoginRequiredMixin, ListView):
    model = Course
    template_name = 'courses/my_course_list.html'
    context_object_name = 'courses'

    def get_queryset(self):
        return Course.objects.filter(teacher=self.request.user)
    
class CourseDetailView(DetailView):
    model = Course
    template_name = 'courses/course_detail.html'
    context_object_name = 'course'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_object()
        context['available_slots'] = [slot for slot in course.time_slots.all() if slot.is_available]
        return context

class CourseCreateView(LoginRequiredMixin, View):
    template_name = 'courses/course_form.html'
    def get(self, request, *args, **kwargs):
        form = CourseForm()
        return render(request, self.template_name, { 'form': form })
    
    def post(self, request, *args, **kwargs):
        form = CourseForm(request.POST, request.FILES)
        
        if form.is_valid():
            course = form.save(commit=False)
            course.teacher = request.user
            course.save()

            generate_timeslots_for_course(course, capacity=1)
            return redirect('provider_dashboard')
           
        return render(request, self.template_name, {
            'form': form,
        })

    
def generate_timeslots_for_course(course, capacity=1):
    if not course.start_date or not course.end_date:
        print(" ABORT: missing start/end date")
        return

    if not course.available_days or not course.daily_start_time or not course.daily_end_time:
        print(" ABORT: missing days or times")
        return
    # 2) Parse available_days safely
    raw = course.available_days
    parts = []
    try:
        if raw.strip().startswith('['):
            data = ast.literal_eval(raw)
            if isinstance(data, (list, tuple)):
                parts = [str(x) for x in data]
            else:
                parts = [str(data)]
        else:
            parts = [p.strip() for p in raw.split(',') if p.strip()]
    except Exception as e:
        print(" ERROR parsing available_days:", e)
    cleaned = raw.replace('[', '').replace(']', '').replace("'", '').replace('"', '')
    parts = [p.strip() for p in cleaned.split(',') if p.strip()]

    allowed_days = [int(d) for d in parts]

    # 3) Actually create slots
    current = course.start_date
    created = 0
    while current <= course.end_date:
        if current.weekday() in allowed_days:
            start_dt = datetime.combine(current, course.daily_start_time)
            end_dt = datetime.combine(current, course.daily_end_time)
            print(" creating slot:", start_dt, "→", end_dt)
            TimeSlot.objects.create(
            course=course,
            capacity=capacity,
            start_time=start_dt,
            end_time=end_dt,
            )
            created += 1
        current += timedelta(days=1)





class WeeklyScheduleView(LoginRequiredMixin, TemplateView):
    template_name = 'courses/weekly_schedule.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        course = get_object_or_404(Course, pk=kwargs['pk'])
        ctx['course'] = course

        start_str = self.request.GET.get('start')
        if start_str:
            try:
                week_start = datetime.strptime(start_str, '%Y-%m-%d').date()
            except ValueError:
                today = timezone.localdate()
                week_start = today - timedelta(days=today.weekday())
        else:
            today = timezone.localdate()
            week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=7)

        timeslots = (
            course.time_slots
            .filter(start_time__date__gte=week_start, start_time__date__lt=week_end)
            .select_related('course')
            .prefetch_related('bookings')
        )

        slot_map = {}
        for ts in timeslots:
            current = ts.start_time
            end = ts.end_time
            while current < end:
                date = current.date()
                hour = current.hour
                if week_start <= date < week_end:
                    key = (date, hour)
                    slot_map[key] = ts
                current += timedelta(hours=1)
        days = [week_start + timedelta(days=i) for i in range(7)]
        ctx['days'] = days

        hours = []
        for h in range(24):
            row_cells = []
            for d in days:
                ts = slot_map.get((d, h))
                if ts: 
                    status = 'available' if ts.is_available else 'full'
                else:
                    status = 'empty'
                row_cells.append({
                    'date': d,
                    'slot': ts,
                    'status': status,
                })
            hours.append({ 'hour': h, 'cells': row_cells })
        ctx['hours'] = hours
        ctx['week_start'] = week_start
        ctx['week_end'] = week_end - timedelta(days=1)

        ctx['prev_start'] = week_start -timedelta(days=7)
        ctx['next_start'] = week_start + timedelta(days=7)
        return ctx



class TimeSlotCreateView(LoginRequiredMixin, CreateView):
    model = TimeSlot
    form_class = TimeSlotForm
    template_name = 'courses/timeslot_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.course = get_object_or_404(Course, pk=kwargs['pk'], teacher=request.user)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        course = self.course
        form.instance.course = course
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('courses:course_detail', args=[self.course.pk])
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['course'] = self.course
        return ctx



@login_required
def add_to_cart(request, pk):
    slot = get_object_or_404(TimeSlot, pk=pk)
    if not slot.is_available:
        messages.error(request, "This time slot is no longer available.")
        return redirect('courses:weekly_schedule', pk=slot.course.pk)
    cart = request.session.get('cart', [])
    if pk not in cart:
        cart.append(pk)
        request.session['cart'] = cart
        request.session.modified = True
        messages.success(request, "Time slot added to cart.")
    else:
        messages.info(request, "Time slot is already in your cart.")
    return redirect('courses:view_cart')

@login_required
def view_cart(request):
    cart = request.session.get('cart', [])
    slots = TimeSlot.objects.filter(pk__in=cart).select_related('course')
    total_amount = sum(slot.course.price for slot in slots)
    context = {
        'slots': slots,
        'total_amount': total_amount,
    }
    return render(request, 'courses/cart.html', context)


@login_required
def remove_from_cart(request, pk):
    cart = request.session.get('cart', [])

    cart = [int(x) for x in cart ]
    if pk in cart:
        cart.remove(pk)
        request.session['cart'] = cart
        request.session.modified = True
        messages.success(request, "Time slot removed from cart.")
    else:
        messages.info(request, "Time slot was not in your cart.")
    return redirect('courses:view_cart')


@login_required
def cart_checkout(request):
    cart = request.session.get('cart', [])
    if request.method != 'POST' or not cart:
        messages.error(request, "Your cart is empty.")
        return redirect('courses:view_cart')

    slots = TimeSlot.objects.filter(pk__in=cart).select_related('course')
    if not slots:
        messages.error(request, "Your cart is empty.")
        return redirect('courses:view_cart')

    YOUR_DOMAIN = request.build_absolute_uri('/')[:-1]

    line_items = []
    timeslot_ids = []

    for slot in slots:
        line_items.append({
        'price_data': {
        'currency': 'usd',
        'unit_amount': slot.course.price, 
        'product_data': {
        'name': f"{slot.course.title} - {slot.start_time}",
        },
        },
        'quantity': 1,
        })
        timeslot_ids.append(str(slot.pk))

    checkout_session = stripe.checkout.Session.create(
    payment_method_types=['card'],
    mode='payment',
    customer_email=request.user.email or None,
    line_items=line_items,
    metadata={
    'timeslot_ids': ','.join(timeslot_ids),
    'user_id': request.user.id,
    },
    success_url=YOUR_DOMAIN + reverse('courses:cart_payment_success') + '?session_id={CHECKOUT_SESSION_ID}',
    cancel_url=YOUR_DOMAIN + reverse('courses:cart_payment_cancel'),
    )

    # optional: keep cart until success, or clear now
    request.session['cart'] = []
    request.session.modified = True

    return redirect(checkout_session.url)


@login_required
def cart_payment_success(request):
    session_id = request.GET.get('session_id')
    if not session_id:
        messages.error(request, "Missing payment session.")
        return redirect('home')

    session = stripe.checkout.Session.retrieve(session_id)
    timeslot_ids_str = session.metadata.get('timeslot_ids', '')
    timeslot_ids = [tid for tid in timeslot_ids_str.split(',') if tid]

    if not timeslot_ids:
        messages.error(request, "No time slots found in payment session.")
        return redirect('home')

    now = timezone.now()
    created_bookings = []

    for ts_id in timeslot_ids:
        slot = TimeSlot.objects.get(pk=ts_id)
        booking = Booking.objects.create(
        student=request.user,
        timeslot=slot,
        status='confirmed',
        stripe_session_id=session_id,
        paid_at=now,
        )
        created_bookings.append(booking)

        teacher = slot.course.teacher
        teacher_email = getattr(teacher, 'email', None)
        if teacher_email:
            teacher_subject = "New Class Booking Confirmed"
            teacher_message = (
                f"Dear {teacher.get_username()},\n\n"
                f"A new booking has been confirmed for your course '{slot.course.title}'.\n"
                f"Student: {request.user.get_username()}\n"
                f"Time: {slot.start_time.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Please contact the student to proceed with the class arrangements.\n\n"
                f"Student Contact Email: {request.user.email}\n\n"
                f"Best regards, \n"
                f"TradeSocial ThirdSpace Support Team"
            )
            send_mail(
                teacher_subject,
                teacher_message,
                settings.DEFAULT_FROM_EMAIL,
                [teacher_email],
                fail_silently=True,
            )
        
    student_email = request.user.email
    if student_email:
        lines = []
        for booking in created_bookings:
            slot = booking.timeslot
            lines.append(
                f"_ {slot.course.title} at {slot.start_time.strftime('%Y-%m-%d %H:%M')}"
                f"(Teacher: {slot.course.teacher.get_username()})"
            )
        student_subject = "Your Class Booking Confirmation"
        student_message = (
            f"Dear {request.user.get_username()},\n\n"
            f"Thank you for your payment. Your bookings have been confirmed for the following classes:\n\n"
            f"{chr(10).join(lines)}\n\n"
            f"Should you not be able to attend any of these classes, please contact your teachers to arrange the class details. Teacher's email: {teacher.email}\n\n"
            f"Best regards,\n"
            f"TradeSocial ThirdSpace Support Team"
        )
        send_mail(
            student_subject,
            student_message,
            settings.DEFAULT_FROM_EMAIL,
            [student_email],
            fail_silently=True,
        )

    messages.success(request, "Payment successful. Your classes have been booked!")
    return redirect('some_dashboard_or_schedule') 


@login_required
def cart_payment_cancel(request):
    messages.info(request, "Payment was cancelled.")
    return render(request, 'courses/payment_cancel.html')


