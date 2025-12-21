"""
URL configuration for broker_portal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", core_views.dashboard, name="dashboard"),
    path("clients/", include(("core.urls.clients", "clients"), namespace="clients")),  # Legacy - all clients
    path("company-clients/", include(("core.urls.company_clients", "company_clients"), namespace="company_clients")),
    path("my-clients/", include(("core.urls.my_clients", "my_clients"), namespace="my_clients")),
    path("exchanges/", include(("core.urls.exchanges", "exchanges"), namespace="exchanges")),
    path("transactions/", include(("core.urls.transactions", "transactions"), namespace="transactions")),
    path("pending/", include(("core.urls.pending", "pending"), namespace="pending")),
    path("reports/", include(("core.urls.reports", "reports"), namespace="reports")),
    path("company-share/", include(("core.urls.company", "company"), namespace="company_share")),
    path("settings/", core_views.settings_view, name="settings"),
    path("login/", core_views.login_view, name="login"),
    path("logout/", core_views.logout_view, name="logout"),
]
