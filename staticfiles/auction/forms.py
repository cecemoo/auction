from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import AuctionItem,Offer, AuctionImage, AuctionVideo, Category
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm 


class AuctionItemForm(forms.ModelForm):
    class Meta:
        model = AuctionItem
        fields = [
        "title",
        "category",
        "short_description",
        "description_document",
        "quantity",
        'starting_price',
        "condition",
        "start_datetime",
        "duration_minutes",
        ]
        widgets = {
        "start_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean_unit_of_measure(self):
        unit_of_measure = self.cleaned_data.get("unit_of_measure")
        if not unit_of_measure:
            return None
        return unit_of_measure.strip()


class RequiredImageFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        images_count = 0
        for form in self.forms:
            if form.cleaned_data.get('DELETE'):
                continue
            image = form.cleaned_data.get('image')
            if image:
                images_count += 1
        if images_count == 0:
            raise ValidationError("At least one image is required.")


class AuctionImageForm(forms.ModelForm):
    class Meta:
        model = AuctionImage
        fields = ["image"]

    def clean(self):
        cleaned = super().clean()
        
        return cleaned
    

AuctionImageFormSet = inlineformset_factory(
    AuctionItem,
    AuctionImage,
    form=AuctionImageForm,
    formset=RequiredImageFormSet,
    extra=3,
    can_delete=True,
    max_num=10,
    validate_max=True,
    )


class AuctionVideoForm(forms.ModelForm):
    class Meta:
        model = AuctionVideo
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        video_file = cleaned.get("video_file")
        video_url = cleaned.get("video_url")
        if not video_file and not video_url:
            return cleaned
        return cleaned

AuctionVideoFormSet = inlineformset_factory(
    AuctionItem,
    AuctionVideo,
    form = AuctionVideoForm,
    extra=2,
    can_delete=True,
    max_num=5,
    validate_max=True,
)


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["offer_price"]

    def clean_offer_price(self):
        price = self.cleaned_data["offer_price"]
        if price <= 0:
            raise ValidationError("Offer must be greater than 0.")
        return price



class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    signup_as_provider = forms.BooleanField(required=False, label="Sign up as provider")
    display_name = forms.CharField(max_length=200, required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email address is already registered.")
        return email




class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = '__all__'