from django.contrib import admin
from .models import Provider, Category, AuctionItem, Offer, AuctionResult, AuctionImage, AuctionVideo



class AuctionImageInline(admin.TabularInline):
    model = AuctionImage
    extra = 1


class AuctionVideoInline(admin.TabularInline):
    model = AuctionVideo
    extra = 1

class AuctionItemAdmin(admin.ModelAdmin):
    inlines = [AuctionImageInline, AuctionVideoInline]
    list_display = ('title', 'provider', 'category','created_at')
    search_fields = ('title',)
   
admin.site.register(Provider)
admin.site.register(Category)
admin.site.register(AuctionItem, AuctionItemAdmin)
admin.site.register(Offer)
admin.site.register(AuctionResult)

