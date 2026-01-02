from django.urls import path
from . import views
from .views import WeeklyScheduleView

app_name = 'courses'

urlpatterns = [
    path('course_list/', views.CourseListView.as_view(), name='course_list'),
    path('my_courses/', views.MyCourseListView.as_view(), name='my_courses'),
    path('course_create/', views.CourseCreateView.as_view(), name='course_create'),
    path('course_detail/<int:pk>/', views.CourseDetailView.as_view(), name='course_detail'),

    path('<int:pk>/schedule/', WeeklyScheduleView.as_view(), name='weekly_schedule'),
    path('<int:pk>/timeslot/add/', views.TimeSlotCreateView.as_view(), name='timeslot_add'),

    path('timeslot/<int:pk>/add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/remove/<int:pk>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/checkout/', views.cart_checkout, name='cart_checkout'),
    path('cart/success/', views.cart_payment_success, name='cart_payment_success'),
    path('cart/cancel/', views.cart_payment_cancel, name='cart_payment_cancel'),

    
    
]