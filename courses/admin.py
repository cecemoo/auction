from django.contrib import admin
from .models import Course, TimeSlot, Booking
# Register your models here.

admin.site.register(Course)
admin.site.register(TimeSlot)
admin.site.register(Booking)