from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponseForbidden

from .models import AuctionItem, AuctionImage, AuctionVideo, Offer, AuctionResult, Provider
from .forms import (
AuctionItemForm,
AuctionImageFormSet,
AuctionVideoFormSet,
OfferForm,
RegistrationForm,
CategoryForm,
)
from django.db.models import Prefetch
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import user_passes_test

def home(request):
    now = timezone.now()
    items = (AuctionItem.objects.filter(is_active=True).order_by("-created_at"))

    paginator = Paginator(items, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    user_is_provider = False
    if request.user.is_authenticated:
        try:
            request.user.provider_profile
            user_is_provider = True
        except ObjectDoesNotExist:
            user_is_provider = False

    return render(request, "auction/home.html", {
        "items": items,
        "page_obj": page_obj,
        "user_is_provider": user_is_provider
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, "Login successful.")
                return redirect("home")
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, "auction/login.html", {"form": form})

@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("home")         


@login_required
def create_auction_item(request):
# assume the logged-in user IS a Provider
    provider = get_object_or_404(Provider, user=request.user)

    if request.method == "POST":
        form = AuctionItemForm(request.POST, request.FILES)
        
        if form.is_valid():
            auction_item = form.save(commit=False)
            auction_item.provider = provider
            auction_item.starting_price = form.cleaned_data["starting_price"] 
            auction_item.save()

            image_formset = AuctionImageFormSet(request.POST, request.FILES, instance=auction_item)
            video_formset = AuctionVideoFormSet(request.POST, request.FILES, instance=auction_item)

            if image_formset.is_valid() and video_formset.is_valid():
                image_formset.save()
                video_formset.save()
                return redirect("provider_dashboard")
        else:
            image_formset = AuctionImageFormSet(request.POST, request.FILES)
            video_formset = AuctionVideoFormSet(request.POST, request.FILES)
       
    else:
        form = AuctionItemForm()
        image_formset = AuctionImageFormSet()
        video_formset = AuctionVideoFormSet()

    return render(request, "auction/create_item.html", {
    "form": form,
    "image_formset": image_formset,
    "video_formset": video_formset,
    })


def auction_item_detail(request, pk):

    item = get_object_or_404(AuctionItem, pk=pk)
    offer_form = None
    can_offer = item.is_active and timezone.now() < item.end_datetime

    if request.method == "POST":
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Login required to make an offer.")
        if request.user == item.provider.user:
            return HttpResponseForbidden("You cannot make an offer on your own items.")

        if can_offer:
            offer_form = OfferForm(request.POST)
        if offer_form.is_valid():
            offer = offer_form.save(commit=False)
            offer.auction_item = item
            offer.customer = request.user
            offer.save()
            # Provider will review offers in dashboard.
            return redirect("auction_item_detail", pk=item.pk)
        else:
            offer_form = OfferForm()
    else:
        if can_offer:
            offer_form = OfferForm()
    offers = item.offers.all().order_by("-created_at")

    return render(request, "auction/item_detail.html", {
    "item": item,
    "offer_form": offer_form,
    "can_offer": can_offer,
    "offers": offers,
    })


@login_required
def provider_dashboard(request):
    provider = get_object_or_404(Provider, user=request.user)
    my_items = AuctionItem.objects.filter(provider=provider).order_by("-created_at")
    offers_by_item = {}
    for item in my_items:
        offers = item.offers.order_by("-created_at")
        offers_by_item[item.pk] = offers
        item.has_accepted_offer = offers.filter(accepted=True).exists()
        item.has_offers = offers.exists()

    return render(request, "auction/provider_dashboard.html", {
    "my_items": my_items,
    "offers_by_item": offers_by_item,
    })


@login_required
def accept_offer(request, item_id, offer_id):
    provider = get_object_or_404(Provider, user=request.user)
    item = get_object_or_404(AuctionItem, pk=item_id, provider=provider)
    offer = get_object_or_404(Offer, pk=offer_id, auction_item=item)
    if offer.auction_item.provider.user != request.user:
        return HttpResponseForbidden("You are not authorized to accept this offer.")
    if item.offers.filter(accepted=True).exists():
        return HttpResponseForbidden("This auction already has an accepted offer.")

    if request.method == "POST":
        offer.accepted = True
        offer.save()
        item.starting_price = offer.offer_price
        item.save()
       
        return redirect("provider_dashboard")

    return HttpResponseForbidden("POST required")


@login_required
def close_auction(request, item_id, winning_offer_id=None):
    provider = get_object_or_404(Provider, user=request.user)
    item = get_object_or_404(AuctionItem, pk=item_id, provider=provider)
    if item.offers.exists():
        return HttpResponseForbidden("This auction has offers and cannot be closed at this time.")
    if request.method == "POST":
        item.is_active = False
        item.save()
        return redirect("provider_dashboard")
    return HttpResponseForbidden("POST required")
    


@login_required
def customer_dashboard(request):

    results = AuctionResult.objects.filter(customer=request.user).select_related(
    "auction_item", "provider", "auction_item__category"
    )

    return render(request, "auction/customer_dashboard.html", {
    "results": results,
    })


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            if form.cleaned_data.get('signup_as_provider'):
                display_name = form.cleaned_data.get('display_name') or user.username
                Provider.objects.create(user=user, display_name=display_name)
            return redirect('login')
    else:
        form = RegistrationForm()

    context = {"form": form}
    return render(request, "auction/register.html", context)



@user_passes_test(lambda u: u.is_superuser)
def create_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = CategoryForm()

    context = {"form": form}
    return render(request, "auction/create_category.html", context)