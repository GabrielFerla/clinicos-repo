from django.apps import AppConfig


class ThemeConfig(AppConfig):
    """App de tema (django-tailwind).

    Hospeda a configuração do Tailwind CSS, o ``base.html`` e os componentes
    HTML reutilizáveis (``templates/components/``). Não tem models nem views —
    é puramente assets/markup.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.theme"
