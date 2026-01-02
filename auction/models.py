from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from urllib.parse import urlparse, parse_qs
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings as setting
from django.core.exceptions import ValidationError
from decimal import Decimal




User = get_user_model()

class Provider(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="provider_profile")
    display_name = models.CharField(max_length=200)

    def __str__(self):
        return self.display_name


class Category(models.Model):

    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class AuctionItem(models.Model):
    CONDITION_CHOICES = [
    ("NEW", "NEW"),
    ("ALMOST_NEW", "ALMOST NEW"),
    ("USED_GOOD", "USED IN GOOD CONDITION"),
    ("USED", "USED"),
    ]

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="auction_items")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="auction_items")
    title = models.CharField(max_length=200, help_text="Title of the auction item", blank=True, null=True)
    short_description = models.CharField(max_length=255)
    # Full description: PDF / WORD upload (optional)
    description_document = models.FileField(
    upload_to="auction/descriptions/",
    blank=True,
    null=True,
    help_text="Optional PDF or Word doc with full presentation"
    )
    
    quantity_available = models.PositiveIntegerField(null=True, blank=True,
    help_text="Quantity available for sale"
    )
    unit_of_measure = models.CharField(
    max_length=50,
    blank=True,
    null=True,
    help_text='Unit of Measure'
    )
    unit_price = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    blank=True,
    null=True,
    help_text="Buy unit price"
    )
    total_price = models.DecimalField(
    max_digits=10,
    decimal_places=2, help_text="Total price (calculated as quantity_available * unit price)", null=True, blank=True
    )
    # asking_price = models.DecimalField(
    # max_digits=10,
    # decimal_places=2,
    # blank=True,
    # null=True,
    # help_text="Optional asking price (if different from total price)"
    # )

    condition = models.CharField(
    max_length=20,
    choices=CONDITION_CHOICES,
    default="NEW"
    )
   
    start_datetime = models.DateTimeField(
    help_text="ITEM AUCTION Starting DATE & TIME"
    )
    duration_days = models.PositiveIntegerField(default=1, null=True, blank=True,
    help_text="DURATION in days (merchant-controlled)"
    )

    # Status control
    is_active = models.BooleanField(
    default=True,
    help_text="If False, auction is considered closed/terminated by provider."
    )
    is_cloased = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    
    # adjust total price when quantity or unit price changes
    def calc_total_for_quantity(self, qty: int) -> Decimal:
        if qty is None:
            qty = 1
        return self.unit_price * Decimal(qty)
    
    def save(self, *args, **kwargs):
        if self.quantity_available is not None and self.unit_price is not None:
            self.total_price = self.quantity_available * self.unit_price
        super().save(*args, **kwargs)

    # TIME ENDS = start + duration
    @property
    def end_datetime(self):
        duration = self.duration_days or 0
        return self.start_datetime + timedelta(days=duration)

    # TIME REMAINING (for display)
    @property
    def time_remaining(self):
        if not self.is_active:
            return "Auction closed"
        now = timezone.now()
        if now >= self.end_datetime:
            return "Expired"
        delta = self.end_datetime - now
       
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes = remainder // 60
        if days > 0:
            return f"{days}d {hours}h {minutes}m remaining"
        elif hours > 0:
            return f"{hours}h {minutes}m remaining"
        else:
            return f"{minutes}m remaining"
       

    # def close_auction(self, *, by_provider=False):
    #     has_offers = self.offers.exists()
    #     if by_provider and has_offers:
    #         raise ValidationError("This auction has offers and cannot be closed at this time.")
    #     self.is_active = False
    #     self.save()
    def remaining_quantity(self) -> int:
        return max(self.quantity_available - self.quantity_sold, 0)
    
    def mark_closed_if_sold_out(self):
        if self.remaining_quantity() <= 0:
            self.is_closed = True
            self.save(update_fields=["is_cloased"])


class AuctionImage(models.Model):

    auction_item = models.ForeignKey(AuctionItem, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="auction/images/", blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.auction_item}"


class AuctionVideo(models.Model):

    auction_item = models.ForeignKey(AuctionItem, on_delete=models.CASCADE, related_name="videos")
    video = models.FileField(upload_to="auction/videos/", blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    video_url = models.URLField(blank=True, null=True)

    @property
    def embed_url(self):
        u = (self.video_url or "").strip()
        if not u: 
            return None
        parsed = urlparse(u)
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""
        query = parsed.query or ""


        if "youtube.com" in host:
            if path == "/watch":
                q = parse_qs(query)
                vid = q.get("v", [None])[0]
                if vid:
                    return f"https://www.youtube.com/embed/{vid}"
            if path.startswith("/embed"):
                vid = path.split("/embed/")[1]
                vid = vid.split("?")[0]
                return f"https://www.youtube.com/embed/{vid}"
            if path.startswith("/shorts"):
                vid = path.split("/shorts/")[1]
                vid = vid.split("?")[0]
                return f"https://www.youtube.com/embed/{vid}"
            

        if "youtu.be" in host:
            vid = path.lstrip("/")
            return f"https://www.youtube.com/embed/{vid}"
        
        if "vimeo.com" in host:
            vid = path.lstrip("/").split("/")[0]
            return f"https://player.vimeo.com/video/{vid}"
        
        return u
        
    def __str__(self):
        return f"Video for {self.auction_item}"


class Offer(models.Model):

    STATUS_DRAFT = "DRAFT"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_WITHDRAWN = "WITHDRAWN"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_WITHDRAWN, "Withdrawn"),
    ]

    auction_item = models.ForeignKey(AuctionItem, on_delete=models.CASCADE, related_name="offers")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="offers")
    offer_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    
    offer_quantity = models.PositiveIntegerField(default=1, help_text="Quantity customer wants to buy")
    offer_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, help_text="Offer price per unit")
  
    accepted = models.BooleanField(default=False)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)

    def submit(self):
        if self.status != self.STATUS_DRAFT:
            return
        self.status = self.STATUS_SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_at"])

    def save(self, *args, **kwargs):
        if self.offer_unit_price is None and hasattr(self.auction_item, "unit_price"):
            self.offer_unit_price = self.auction_item.unit_price

        if self.offer_unit_price is not None:
            self.offer_price = Decimal(self.offer_unit_price) * self.offer_quantity
        super().save(*args, **kwargs)

    def accept(self):
        item = self.auction_item
        if self.offer_quantity > item.remaining_quantity():
            return
        
        self.accepted = True
        self.save(update_fields=["accepted"])

        item.quantity_sold = item.quantity_sold + self.offer_quantity
        item.save(update_fields=["quantity_sold"])
        item.mark_closed_if_sold_out()

    def __str__(self):
        return f"Offer {self.offer_price} on {self.auction_item} by {self.customer}"


class AuctionResult(models.Model):

    auction_item = models.OneToOneField(AuctionItem, on_delete=models.CASCADE, related_name="result")
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="results")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="purchases")

    qty = models.DecimalField(max_digits=10, decimal_places=2)
    unit_of_measure = models.IntegerField(null=True, blank=True)
    offer_quantity = models.ForeignKey(Offer, on_delete=models.SET_NULL, null=True, blank=True)
    condition = models.CharField(max_length=20)

    merchant_price = models.DecimalField(max_digits=10, decimal_places=2) 
    sold_price_total = models.DecimalField(max_digits=10, decimal_places=2)

    start_datetime = models.DateTimeField()
    sold_datetime = models.DateTimeField(default=timezone.now)

    # shipped_delivered = models.BooleanField(default=False)
    # received_accepted = models.BooleanField(default=False)

    def __str__(self):
        return self.auction_item.title



@receiver(pre_save, sender=Offer)
def send_email_when_offer_is_accepted(sender, instance, **kwargs):
    if not instance.accepted:
        return
    auction_item = instance.auction_item
    offer_quantity = instance.offer_quantity
    bidder_user = instance.customer
    provider_obj = getattr(auction_item, "provider", None)
    if provider_obj is not None and hasattr(provider_obj, "user"):
        provider_user = provider_obj.user
    else:
        provider_user = provider_obj
    
    if not provider_user:
        return
        
    item_name = getattr(auction_item, "title", str(auction_item))
    offer_quantity = getattr(instance, "offer_quantity", None)
    price = instance.offer_price

    send_mail(
            subject=f"You accepted an offer for {item_name}",
            message =(f"Dear {provider_user.get_username()},\n"
                      f"You accepted an offer of {price} for {item_name} for {offer_quantity} from {bidder_user.get_username()}.\n"
                      f"Please contact the buyer to proceed with the transaction.\n{bidder_user.email}"
                      f"\n\nTradeSocial Auction Support Team"),
            from_email=getattr(setting, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[provider_user.email],
            fail_silently=True,

        )

    send_mail(
            subject=f"Your offer for {item_name} was accepted",
            message =(f"Dear {bidder_user.get_username()},\n"
                      f"Congratulations! Your offer of {price} for {item_name} for {offer_quantity} was accepted by the provider {provider_user.get_username()}.\n"
                      f"Please contact the provider to proceed with the transaction.\n{provider_user.email}"
                      f"\n\nTradeSocial Auction Support Team"),
            from_email=getattr(setting, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[bidder_user.email],
            fail_silently=True,
        )


@receiver(post_save, sender=Offer)
def create_result_when_offer_is_accepted(sender, instance, created, **kwargs):
    if not instance.accepted:
        return
    item = instance.auction_item
    if hasattr(item, "result"):
        return 
    
    AuctionResult.objects.create(
        auction_item=item, 
        provider=item.provider,
        customer=instance.customer,
        qty=item.quantity_available,
        
        condition=item.condition,
        merchant_price=item.total_price,
        sold_price_total=instance.offer_price,
        start_datetime=item.start_datetime,
        sold_datetime=timezone.now(),
    )
    if item.is_active:
        item.is_active = False
        item.save(update_fields=['is_active'])

    item.quantity_available -= 1
    if item.quantity_available <= 0:
        item.is_active = False
    item.save(update_fields=['quantity_available', 'is_active'])