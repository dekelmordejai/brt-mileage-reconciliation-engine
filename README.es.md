# Motor de conciliación de kilometraje BRT

[English](README.md) · [Arquitectura](docs/architecture.md) · [Ejecutar demo](docs/demo.md) · [Alcance real](docs/status.md)

Aplicación de ingeniería de datos para separar programación, kilómetros físicos reportados, cobertura revisada y elegibilidad económica. Python, FastAPI, SQLite e interfaz de análisis en navegador.

Esta edición pública es una demostración independiente de portafolio. Todos los registros y capturas incluidos son sintéticos. No representa un producto oficial de una agencia de transporte, no incluye expedientes operativos y no ejecuta pagos. El historial público comienza en una instantánea revisada, sin casos ni datos privados.

## Flujo ejecutable

Importar CSV/XLSX/JSON → validar fuentes y conservar originales → procesar → buscar viajes y evidencias → proponer segmentos → revisión por otra persona → reprocesar → exportar Excel/CSV/JSON y comprobar auditoría.

- Programación independiente del vehículo asignado; tarifa según tipo real y vigencia.
- Los estados administrativos no borran kilómetros físicos.
- Segmentos disjuntos, exclusividad de evidencias, detección de duplicados/solapamientos y bloqueos documentales localizados.
- Propuestas versionadas, roles persistentes y ejecuciones inmutables.
- Interempresas, tarifas ambiguas y reglas no confirmadas permanecen pendientes.

<img src="docs/assets/demo-dashboard.png" alt="Tablero con datos exclusivamente sintéticos" width="1000">

## Probar en Windows

Con Python 3.12 instalado, desde la raíz:

```powershell
.\scripts\start.ps1 -Demo
```

Abrir http://127.0.0.1:8000. Usuarios sintéticos: `demo-admin`, `demo-analista`, `demo-revisor`; contraseña exclusiva de demo: `Demo-local-2026!`. No usar estas cuentas con datos reales. La [guía](docs/demo.md) incluye instalación manual y Docker.

## Verificación y límites

Base revisada: 52 pruebas aprobadas, 3 preguntas de diseño omitidas expresamente y flujo completo probado en navegador. GitHub Actions comprueba Python 3.11–3.13, navegador sintético, paquete y construcción Docker. No se declara exactitud financiera ni uso institucional en producción.

La reconstrucción espacial automática, el cierre/redondeo contractual y la aceptación de reglas por una organización no están resueltos. SQLite se limita a una instancia local. La reconstrucción/revisión manual por segmentos sí funciona. Ninguna propuesta autoriza una liquidación real.

Ver [arquitectura](docs/architecture.md), [alcance verificado](docs/status.md), [seguridad](SECURITY.md) y [descripción para CV](docs/portfolio.md).

Repositorio público para revisión de portafolio, sin otorgamiento de licencia de código abierto. Se conserva la reserva de derechos; ver [LICENSE.md](LICENSE.md).
