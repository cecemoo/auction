from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    path("item/<int:pk>/", views.auction_item_detail, name="auction_item_detail"),
    
    path("provider/create/", views.create_auction_item, name="create_auction_item"),
    path("provider/dashboard/", views.provider_dashboard, name="provider_dashboard"),
    path("provider/<int:item_id>/accept/<int:offer_id>/", views.accept_offer, name="accept_offer"),
    path("provider/<int:item_id>/close/", views.close_auction, name="close_auction"),

    path("customer/dashboard/", views.customer_dashboard, name="customer_dashboard"),

    path('register/', views.register, name='register'),

    path('create_category/', views.create_category, name='create_category'),
]

