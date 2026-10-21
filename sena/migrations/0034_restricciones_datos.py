from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [('sena', '0033_usuario_verificacion_correo')]

    operations = [
        migrations.AddConstraint(
            model_name='producto',
            constraint=models.CheckConstraint(condition=Q(('precio__gte', 0)), name='producto_precio_no_negativo'),
        ),
        migrations.AddConstraint(
            model_name='producto',
            constraint=models.CheckConstraint(condition=Q(('stock__gte', 0)), name='producto_stock_no_negativo'),
        ),
        migrations.AddConstraint(
            model_name='pedido',
            constraint=models.CheckConstraint(condition=Q(('total__gte', 0)), name='pedido_total_no_negativo'),
        ),
        migrations.AddConstraint(
            model_name='pedidoproducto',
            constraint=models.CheckConstraint(condition=Q(('cantidad__gt', 0)), name='pedido_producto_cantidad_positiva'),
        ),
        migrations.AddConstraint(
            model_name='pedidoproducto',
            constraint=models.CheckConstraint(condition=Q(('precio__gte', 0)), name='pedido_producto_precio_no_negativo'),
        ),
        migrations.AddConstraint(
            model_name='calificacion',
            constraint=models.CheckConstraint(condition=Q(('puntuacion__gte', 1), ('puntuacion__lte', 5)), name='calificacion_entre_1_y_5'),
        ),
    ]
