from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # auto-login after sign-up
            return redirect('mark_attendance')
    else:
        form = UserCreationForm()
    return render(request, 'auth/signup.html', {'form': form})
