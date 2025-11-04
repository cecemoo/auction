from .models import Provider



def user_role(request):
    user_is_provider = False
    if request.user.is_authenticated:
        user_is_provider = Provider.objects.filter(user=request.user).exists()

    return {'user_is_provider': user_is_provider}
