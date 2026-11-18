# Comparativa de Costes Mensuales (Estimación)

| Proveedor | Servicio de Cómputo | Servicio de Base de Datos | Coste Total Estimado (Mensual) |
| --- | --- | --- | --- |
| Render | Web Service (Starter) - $7.00 | PostgreSQL (Starter) - $7.00 | ~$14.00 |
| Google Cloud | Cloud Run (Pago por uso) - ~$2.00 | Cloud SQL (db-f1-micro) - ~$11.00 | ~$13.00 - $15.00 |
| AWS | EC2 (t4g.micro) o App Runner - ~$8.00 | RDS (db.t4g.micro) - ~$14.00 | ~$22.00 |
| Azure | App Service (B1) - ~$13.00 | Azure Database for PostgreSQL - ~$14.00 | ~$27.00 |

> **Nota:** Los precios están expresados en USD, que es la moneda estándar de facturación en la nube, y no incluyen impuestos aplicables ni el coste del registro del dominio.

## Desglose por Plataforma y Operaciones

### 1. Render (Plataforma como Servicio - PaaS)

Render es la opción con menor fricción operativa. El despliegue se realiza directamente desde el repositorio (GitHub/GitLab) y la plataforma gestiona los certificados SSL y el balanceo de carga automáticamente.

- **Ventaja operativa:** No hay que gestionar el sistema operativo subyacente.
- **Consideración técnica:** Las bases de datos en el plan gratuito se eliminan a los 90 días, por lo que el plan Starter ($7) es obligatorio para retener los datos de los tickets a largo plazo.

### 2. Google Cloud Platform (GCP)

La combinación de Cloud Run (contenedores sin servidor) y Cloud SQL ofrece el equilibrio óptimo entre coste y escalabilidad. Cloud Run escala a cero cuando no hay peticiones, lo que reduce drásticamente la factura si el sistema de tickets tiene poco uso nocturno.

- **Ventaja operativa:** Escalabilidad automática e integración nativa con el ecosistema de Google.
- **Consideración técnica:** Requiere empaquetar la aplicación en un contenedor Docker antes del despliegue.

### 3. Amazon Web Services (AWS)

Desplegar en AWS proporciona acceso al ecosistema de servicios más grande, lo que es ideal si el sistema de tickets planea integrar análisis avanzados o IA en el futuro.

- **Ventaja operativa:** Altísima fiabilidad y control granular sobre la infraestructura.
- **Consideración técnica:** Para mantener el coste bajo (~$22), hay que utilizar instancias basadas en la arquitectura ARM (Graviton - t4g). Si se prefiere evitar la gestión de servidores EC2, AWS Lightsail ofrece un paquete todo en uno (Cómputo + BD) por un precio fijo de unos $15-$20 mensuales.

### 4. Microsoft Azure

Azure App Service facilita la integración si la aplicación está construida en ecosistemas .NET o si los usuarios se autenticarán utilizando el directorio activo (Microsoft Entra ID).

- **Ventaja operativa:** Excelentes integraciones empresariales y herramientas de monitorización (Application Insights).
- **Consideración técnica:** Suele tener un coste base ligeramente superior en las instancias administradas (App Service) comparado con las alternativas puras de Linux en otros proveedores.

## Consideraciones de Arquitectura Segura

Al evaluar estas plataformas, el coste de la infraestructura base es solo el primer paso. Para proteger los datos de los tickets y evitar fugas de información, la superficie de ataque cambia según el proveedor:

- **Aislamiento de Red (VPC):** En AWS y Azure, desplegar la base de datos dentro de una nube privada virtual (VPC) para que no tenga IP pública es gratuito. En plataformas como Render, la base de datos es accesible internamente por defecto, pero se deben configurar listas de control de acceso (ACLs) estrictas si se habilita la conexión externa.
- **Gestión de Parches:** Utilizar servicios serverless o PaaS (Cloud Run, Render, Azure App Service) delega el parcheo del sistema operativo al proveedor. Si se opta por máquinas virtuales puras (como AWS EC2), se asume la responsabilidad de aplicar parches de seguridad contra vulnerabilidades (CVEs) recientes, lo que requiere tiempo de administración.
- **Filtrado de Tráfico:** Si la aplicación comienza a recibir escaneos automatizados o ataques de capa 7 (SQLi, XSS), implementar un Web Application Firewall (WAF) incrementará significativamente el presupuesto. AWS WAF o Azure WAF añaden un mínimo de $20 a $30 mensuales al coste base, mientras que Cloudflare (en su capa gratuita) puede actuar como un proxy inverso protector frente a cualquiera de estas cuatro opciones sin coste adicional inicial.

Los cuatro proveedores ofrecen capas gratuitas (Free Tiers) renovables anualmente o créditos iniciales para cuentas nuevas que pueden reducir el coste del primer año de desarrollo y pruebas a prácticamente cero.
