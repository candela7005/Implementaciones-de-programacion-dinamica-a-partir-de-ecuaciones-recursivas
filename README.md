# Compilador para un Lenguaje de Dominio Específico (DSL) de Programación Dinámica

Este repositorio contiene el desarrollo técnico de un Trabajo de Fin de Grado enfocado en la creación de un compilador capaz de transformar definiciones matemáticas de algoritmos de Programación Dinámica en código fuente ejecutable en C++.

El objetivo del sistema es automatizar la transición entre la formulación de ecuaciones de recurrencia y su implementación imperativa, garantizando la correctitud semántica y facilitando la validación de la lógica algorítmica.

## Funcionalidades del Sistema

* **Validación de Tipos y Estructuras:** Comprobación estricta de tipos de datos (`nat`, `int`, `bool`, `real`, `char`) y soporte para estructuras multidimensionales (`array`).
* **Análisis de Terminación:** Motor semántico diseñado para verificar que las llamadas recursivas dentro de las ecuaciones convergen correctamente hacia los casos base definidos.
* **Soporte para Familias de Programación Dinámica:** Capacidad para procesar y traducir las cuatro topologías fundamentales:
    1. **Selección:** Problema de la Mochila 0/1.
    2. **Intervalos:** Multiplicación de Secuencia de Matrices.
    3. **Dos Secuencias:** LCS (Longest Common Subsequence).
    4. **Caminos 2D:** Camino mínimo en matriz.
* **Generación de Código:** Traducción automática a C++ estándar a partir de la representación intermedia validada.

## Arquitectura del Compilador

La implementación se ha realizado en Python y se estructura en las siguientes fases secuenciales:

1. **Análisis Sintáctico:** Utiliza la librería `lark-parser` para procesar la gramática formal y generar el árbol de derivación inicial.
2. **Representación Intermedia (AST):** La clase `IRBuilder` transforma el árbol de Lark en un Árbol de Sintaxis Abstracta basado en `dataclasses`, eliminando el ruido sintáctico y estructurando la información para su análisis.
3. **Análisis Semántico (`SemanticChecks`):** Realiza la inspección de tipos, la resolución de identificadores y la validación matemática de las dependencias recursivas.
4. **Generación de C++:** Emite el código fuente final basándose en el AST anotado y validado.

## Ejemplo de Definición (Mochila 0/1)

El lenguaje permite expresar el algoritmo de forma declarativa:

```text
nat N, W;
array<nat> v, w;

mochila(0, c) = 0;
mochila(i, 0) = 0;
mochila(i, c) = mochila(i - 1, c) if w[i] > c;
mochila(i, c) = max{ mochila(i - 1, c), v[i] + mochila(i - 1, c - w[i]) } if w[i] <= c;

return mochila(N, W);
