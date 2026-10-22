"""Dudas frecuentes de cultivo (contenido estático)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def faq(request):
    return render(request, "growlog/faq.html")
