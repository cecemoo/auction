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
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="auction_items")
    title = models.CharField(max_length=200, help_text="Title of the auction item", blank=True, null=True)

    # AUCTION ITEM NUMBER (serial within category)
    # item_number = models.CharField(
    # max_length=50,
    # help_text="Serial number of this item in this category"
    # )

   
    short_description = models.CharField(max_length=255)

    # Full description: PDF / WORD upload (optional)
    description_document = models.FileField(
    upload_to="auction/descriptions/",
    blank=True,
    null=True,
    help_text="Optional PDF or Word doc with full presentation"
    )

    quantity = models.IntegerField(
    help_text="Quantity of items available in this auction"
    )
    # unit_of_measure = models.CharField(
    # max_length=50,
    # blank=True,
    # null=True,
    # help_text='Unit of Measure (e.g. "Each", "Pound", "Foot", etc.)'
    # )

    # price_per_unit_of_measure = models.DecimalField(
    # max_digits=10,
    # decimal_places=2,
    # blank=True,
    # null=True,
    # help_text="Merchant starting/list price per Unit of Measure"
    # )

    starting_price = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    blank=True,
    null=True,
    help_text="Starting bid price for the auction"
    )
    # asking_price = models.DecimalField(
    # max_digits=10,
    # decimal_places=2,
    # blank=True,
    # null=True,
    # help_text="Starting price"
    # )

    condition = models.CharField(
    max_length=20,
    choices=CONDITION_CHOICES,
    default="NEW"
    )
   
    start_datetime = models.DateTimeField(
    help_text="ITEM AUCTION Starting DATE & TIME"
    )
    duration_minutes = models.PositiveIntegerField(
    help_text="DURATION in minutes (merchant-controlled)"
    )

    # Status control
    is_active = models.BooleanField(
    default=True,
    help_text="If False, auction is considered closed/terminated by provider."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # class Meta:
    #     unique_together = ("category", "item_number")

    # def __str__(self):
    #     return f"{self.category.name}-{self.item_number}: {self.short_description}"
    
    def save(self, *args, **kwargs):
        if self.quantity is not None and self.starting_price is not None:
            self.starting_price = self.quantity * self.starting_price
        super().save(*args, **kwargs)

    # TIME ENDS = start + duration
    @property
    def end_datetime(self):
        return self.start_datetime + timedelta(minutes=self.duration_minutes)

    # TIME REMAINING (for display)
    @property
    def time_remaining(self):
        if not self.is_active:
            return "Auction closed"
        now = timezone.now()
        if now >= self.end_datetime:
            return "Expired"
        delta = self.end_datetime - now
       
        mins = int(delta.total_seconds() // 60)
        hrs = mins // 60
        mins_left = mins % 60
        return f"{hrs}h {mins_left}m remaining"

    def close_auction(self, *, by_provider=False):
        has_offers = self.offers.exists()
        if by_provider and has_offers:
            raise ValidationError("This auction has offers and cannot be closed at this time.")
        self.is_active = False
        self.save()


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

    auction_item = models.ForeignKey(AuctionItem, on_delete=models.CASCADE, related_name="offers")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="offers")
    offer_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

  
    accepted = models.BooleanField(default=False)

    def __str__(self):
        return f"Offer {self.offer_price} on {self.auction_item} by {self.customer}"


class AuctionResult(models.Model):

    auction_item = models.OneToOneField(AuctionItem, on_delete=models.CASCADE, related_name="result")
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="results")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="purchases")

    qty = models.DecimalField(max_digits=10, decimal_places=2)
    # unit_of_measure = models.CharField(max_length=50)

    # price_per_unit_of_measure = models.DecimalField(max_digits=10, decimal_places=2)
    condition = models.CharField(max_length=20)

    merchant_price = models.DecimalField(max_digits=10, decimal_places=2) 
    sold_price_total = models.DecimalField(max_digits=10, decimal_places=2)

    start_datetime = models.DateTimeField()
    sold_datetime = models.DateTimeField(default=timezone.now)

    # shipped_delivered = models.BooleanField(default=False)
    # received_accepted = models.BooleanField(default=False)

    def __str__(self):
        return f"Result for {self.auction_item} sold to {self.customer}"



@receiver(pre_save, sender=Offer)
def send_email_when_offer_is_accepted(sender, instance, **kwargs):
    if not instance.pk:
        return
    old = Offer.objects.get(pk=instance.pk)
    if old.accepted is False and instance.accepted is True:
        auction_item = instance.auction_item
        bidder_user = instance.customer

        provider_obj = getattr(auction_item, "provider", None)
        if provider_obj is not None and hasattr(provider_obj, "user"):
            provider_user = provider_obj.user
        else:
            provider_user = provider_obj
        if not provider_user:
            return
        
        item_name = getattr(auction_item, "title", str(auction_item))
        price = instance.offer_price

        send_mail(
            subject=f"You accepted an offer for {item_name}",
            message =(f"Dear {provider_user.get_username()},\n"
                      f"You accepted an offer of {price} for {item_name} from {bidder_user.get_username()}.\n"
                      f"Please contact the buyer to proceed with the transaction.\n{bidder_user.email}"
                      f"\n\nTradeSocial Auction Support Team"),
            from_email=getattr(setting, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[provider_user.email],
            fail_silently=True,

        )

        send_mail(
            subject=f"Your offer for {item_name} was accepted",
            message =(f"Dear {bidder_user.get_username()},\n"
                      f"Congratulations! Your offer of {price} for {item_name} was accepted by the provider {provider_user.get_username()}.\n"
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
        qty=item.quantity,
        
        condition=item.condition,
        merchant_price=item.starting_price,
        sold_price_total=instance.offer_price,
        start_datetime=item.start_datetime,
        sold_datetime=timezone.now(),
    )
    if item.is_active:
        item.is_active = False
        item.save(update_fields=['is_active'])