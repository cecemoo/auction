from django import forms
from .models import Course, TimeSlot, WEEKDAY_CHOICES
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from django.utils import timezone




class CourseForm(forms.ModelForm):
    available_days = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label='Teaching days',
    )

    class Meta:
        model = Course
        fields = [
        'title',
        'description',
        'price',
        'duration_minutes',
        'image',
        'video_url',
        'start_date',
        'end_date',
        'available_days',
        'daily_start_time',
        'daily_end_time',
        ]
       
        widgets = {
        'start_date': forms.DateInput(attrs={'type': 'date'}),
        'end_date': forms.DateInput(attrs={'type': 'date'}),
        'daily_start_time': forms.TimeInput(attrs={'type': 'time'}),
        'daily_end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.pk and self.instance.available_days:
                self.initial['available_days'] = self.instance.available_days.split(',')
        

        def clean(self):
            cleaned = super().clean()
            start_date = cleaned.get('start_date')
            end_date = cleaned.get('end_date')
            start_time = cleaned.get('daily_start_time')
            end_time = cleaned.get('daily_end_time')

            if start_date and end_date and end_date < start_date:
                raise ValidationError("End date must be on or after start date.")
            if start_time and end_time and end_time <= start_time:
                raise ValidationError("Daily end time must be after daily start time.")
            return cleaned
        
        def save(self, commit=True):
            obj = super().save(commit=False)
            days = self.cleaned_data.get('available_days', [])
            obj.available_days = ','.join(days)
            if commit:
                obj.save()
            return obj

class TimeSlotForm(forms.ModelForm):
    start_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M'],
    )
    end_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M'],
    )
    class Meta:
        model = TimeSlot
        fields = ['capacity', 'start_time', 'end_time']
        labels = {
             'start_time' : 'Session start (date & time)',
                'end_time' : 'Session end (date & time)',
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')

        if not start or not end:
            return cleaned_data

        if end <= start:
            raise ValidationError("End time must be after start time.")

        # today = timezone.localdate()
        # if start.date() < today:
        #     raise ValidationError("Start time cannot be in the past.")

        course = self.instance.course
        if course:
                if course.start_date and start.date() < course.start_date:
                    raise ValidationError(
        f"Time slot start time must be on or after {course.start_date}."
        )
                if course.end_date and start.date() > course.end_date:
                    raise ValidationError(
        f"Time slot start time must be on or before {course.end_date}."
        )

        return cleaned_data

TimeSlotFormSet = inlineformset_factory(
    Course,
    TimeSlot,
    form=TimeSlotForm,
    extra=5,
    can_delete=True,
)