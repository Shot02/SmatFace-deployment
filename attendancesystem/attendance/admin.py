from django.contrib import admin
from .models import AIMessage, AIFeedback

@admin.register(AIMessage)
class AIMessageAdmin(admin.ModelAdmin):
    list_display = ('content', 'user', 'category', 'source', 'created_at')
    list_filter = ('category', 'source', 'created_at')
    search_fields = ('content', 'user__username')
    readonly_fields = ('created_at',)

@admin.register(AIFeedback)
class AIFeedbackAdmin(admin.ModelAdmin):
    list_display = ('message', 'user', 'is_positive', 'created_at')
    list_filter = ('is_positive', 'created_at')
    search_fields = ('message__content', 'user__username', 'feedback_text')
    readonly_fields = ('created_at',)