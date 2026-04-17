# parser_tfg.py
from lark import Lark, UnexpectedInput, Visitor
from dataclasses import dataclass, field
from typing import List, Optional, Any
from lark import Transformer, Token

GRAMMAR = r"""
start           : programa

programa        : declaraciones ecuaciones inicial

declaraciones   : (declaracion)*
ecuaciones      : (ecuacion)+
inicial         : "return" llamada ";"

declaracion     : tipo IDENT ("," IDENT)? ";"
ecuacion        : llamada "=" expr ("if" expr)? ";"

!tipo            : "nat" | "int" | "real" | "bool" | "char" | "array" "<" tipo ("," IDENT)? ">"

llamada         : IDENT "(" (expr ("," expr)*)? ")" 
reduccion       : (MIN | MAX) "{" rango "}" "("expr")"
                | (MIN | MAX) "{" expr ("," expr)* "}"

rango           : IDENT op_rango IDENT op_rango IDENT
op_rango        : LT | LE

expr           : logica
logica         : cmp ((AND | OR) cmp)*
cmp            : suma ((LT | LE | GT | GE | EQ | NEQ) suma)?
suma           : producto ((PLUS | MINUS) producto)*  
producto       : primario ((MULT | DIV) primario)*
primario       : NUMERO
                | llamada
                | IDENT
                | IDENT ("[" expr "]")+
                | reduccion
                | "(" expr ")"
                
MAX: "max"
MIN: "min"
AND: "and"
OR: "or"
LT: "<"
LE: "<="
GT: ">"
GE: ">="
EQ: "=="
NEQ: "!="
MINUS: "-"
PLUS: "+"
MULT: "*"   
DIV: "/"

%import common.CNAME -> IDENT
%import common.NUMBER -> NUMERO
%import common.WS
COMMENT: "//" /[^\n]/*
%ignore COMMENT
%ignore WS
"""

parser = Lark(GRAMMAR, parser="lalr", propagate_positions=True, maybe_placeholders=False)

# Intermediate Representation
# Usamos una clase vacía para indicar que algo es una expresión matemática
class Expresion: 
    pass

@dataclass
class Numero(Expresion):
    valor: int

@dataclass
class Variable(Expresion):
    nombre: str
    indices: List[Expresion] = field(default_factory=list) # Para cosas como w[i] o d[i-1]
    tipo: Optional[str] = None # Para comprobaciones de tipos

@dataclass
class OperacionBinaria(Expresion):
    izq: Expresion
    operador: str        # '+', '-', '<', 'and', '==', etc.
    der: Expresion

@dataclass
class Rango:
    limite_inf: Expresion
    iterador: Variable        # 'k'
    limite_sup: Expresion
    incluye_sup: bool    # True si es '<=', False si es '<'

@dataclass
class Reduccion(Expresion):
    tipo: str            # 'min' o 'max'
    rango: Optional[Rango] # Presente en min{i <= k < j}(...)
    argumentos: List[Expresion] # Para min{a, b} o la expresión interna del bucle

@dataclass
class Declaracion:
    tipo: str
    nombre: str

@dataclass
class Llamada(Expresion):
    nombre: str
    argumentos: List[Expresion] 

@dataclass
class Ecuacion:
    izq: Llamada
    der: Expresion
    condicion: Optional[Expresion] = None
    es_caso_base: bool = False

@dataclass
class ProgramaDP:
    declaraciones: List[Declaracion] = field(default_factory=list)
    ecuaciones: List[Ecuacion] = field(default_factory=list)
    retorno: Llamada = None


class IRBuilder(Transformer):
    
    def start(self, args): return args[0]

    def programa(self, args):
        decls = args[0] if args[0] else []
        return ProgramaDP(declaraciones=decls, ecuaciones=args[1], retorno=args[2])

    def declaraciones(self, args):
        return [decl for sublist in args for decl in sublist]

    def ecuaciones(self, args): return args
    
    def inicial(self, args): return args[0]

    def tipo(self, args):
        # Une todos los tokens (ej: 'array', '<', 'nat', '>') en un solo string
        return "".join(str(arg.value if isinstance(arg, Token) else arg) for arg in args)

    def declaracion(self, args):
        tipo_base = args[0] # Gracias a def tipo(), esto ya es un string
        idents = args[1:]
        return [Declaracion(tipo=tipo_base, nombre=str(ident.value if isinstance(ident, Token) else ident)) for ident in idents]

    def llamada(self, args):
        nombre = str(args[0].value if isinstance(args[0], Token) else args[0])
        argumentos = args[1:] if len(args) > 1 else []
        return Llamada(nombre=nombre, argumentos=argumentos)

    def ecuacion(self, args):
        izq = args[0]
        der = args[1]
        condicion = args[2] if len(args) > 2 else None
        
        def tiene_recursividad(nodo):
            if isinstance(nodo, Llamada) and nodo.nombre == izq.nombre: return True
            if isinstance(nodo, OperacionBinaria): return tiene_recursividad(nodo.izq) or tiene_recursividad(nodo.der)
            if isinstance(nodo, Reduccion): return any(tiene_recursividad(arg) for arg in nodo.argumentos)
            if isinstance(nodo, Variable): return any(tiene_recursividad(idx) for idx in nodo.indices)
            return False

        es_base = not tiene_recursividad(der)
        return Ecuacion(izq=izq, der=der, condicion=condicion, es_caso_base=es_base)

    def reduccion(self, args):
        tipo_red = str(args[0].value).lower() # max/min
        
        if isinstance(args[1], Rango): # tiene Rango
            rango_obj = args[1]
            expr_interna = args[2]
            return Reduccion(tipo=tipo_red, rango=rango_obj, argumentos=[expr_interna])
            
        else:
            return Reduccion(tipo=tipo_red, rango=None, argumentos=args[1:])
    
    def logica(self, args): return self._construir_binaria(args)
    def expr(self, args): return args[0]
    def cmp(self, args):    return self._construir_binaria(args)
    def suma(self, args):   return self._construir_binaria(args)
    def producto(self, args): return self._construir_binaria(args)

    def _construir_binaria(self, args):
        if len(args) == 1: return args[0]
        nodo = args[0]
        for i in range(1, len(args), 2):
            operador = str(args[i].value if isinstance(args[i], Token) else args[i])
            nodo = OperacionBinaria(izq=nodo, operador=operador, der=args[i+1])
        return nodo

    def primario(self, args):
        if len(args) == 1:
            nodo = args[0]
            if isinstance(nodo, Token):
                if nodo.type == 'NUMERO': return Numero(int(nodo.value))
                if nodo.type == 'IDENT':  return Variable(nombre=str(nodo.value))
            return nodo
            
        if isinstance(args[0], Token) and args[0].type == 'IDENT':
            nombre = str(args[0].value)
            return Variable(nombre=nombre, indices=args[1:])
            
        return args[0]

    def rango(self, args):
        lim_inf = Variable(nombre=str(args[0].value))
        iterador_var = Variable(nombre=str(args[2].value))
        lim_sup = Variable(nombre=str(args[4].value))
        
        # 2. Comprobamos si el segundo operador es '<='
        incluye_sup = (str(args[3].value if isinstance(args[3], Token) else args[3]) == '<=')
        
        return Rango(limite_inf=lim_inf, iterador=iterador_var, limite_sup=lim_sup, incluye_sup=incluye_sup)




class SemanticChecks:
    def __init__(self):
        self.globales = {} # variables globales (Diccionarios para guardar los tipos)
        self.locales = {} # variables locales
        self.func = None
        self.casos_base = [] 
        self.pos_valor = set() # (posicion_parametro, valor_numerico)
        self.relaciones_base = set() # (tipo_relacion, pos1, pos2)
        self.restricciones_activas = [] # Pila para guardar objetos Rango matemáticos
        self.is_rhs = False


    def validar_programa(self, programa):
        """Punto de entrada para validar todo el programa"""
        # 1. Validar declaraciones (variables globales)
        for decl in programa.declaraciones:
            self.declaracion(decl)
            
        # 2. Validar ecuaciones
        for eq in programa.ecuaciones:
            self.ecuacion(eq)
            
        # 3. Validar el retorno inicial
        self.inicial(programa.retorno)

    def comprobacionFunc(self, nombre_func, contexto=""):
        if self.func is None:
            self.func = nombre_func
        elif nombre_func != self.func:
            raise ValueError(f"[Semántico] Función distinta '{nombre_func}' en {contexto}; esperada: '{self.func}'")

    def declaracion(self, decl):
        if decl.nombre in self.globales:
            raise ValueError(f"[Semántico] Identificador duplicado: '{decl.nombre}'")
        self.globales[decl.nombre] = decl.tipo

    def obtener_modificacion(self, nodo):
        """
        Analiza si el nodo tiene la forma (VARIABLE +/- NUMERO).
        Devuelve una tupla (operador, NUMERO) o None.
        """
        if isinstance(nodo, OperacionBinaria) and nodo.operador in ('+', '-'):
            # Comprobamos si el lado derecho es un número: ej. (x - 1) o (i + 2)
            if isinstance(nodo.der, Numero):
                return (nodo.operador, nodo.der.valor)
            # manejar (1 + x)
            elif isinstance(nodo.izq, Numero) and nodo.operador == '+':
                return (nodo.operador, nodo.izq.valor)
        return None

    def llamada(self, nodo):
        self.comprobacionFunc(nodo.nombre, "llamada")

        if self.is_rhs and nodo.nombre == self.func:
            progresa = False

            # 1. Comprobar reducciones relacionales matemáticas (ej. secMatrices)
            if self._verifica_convergencia_relacional(nodo):
                print("se verifica la conv. relacional")
                progresa = True
            else:
                # 2. Comprobar disminuciones directas de parámetros (ej. mochila, LCS)
                for i, arg in enumerate(nodo.argumentos):
                    modificacion = self.obtener_modificacion(arg)
                    
                    if modificacion is not None:
                        operador, paso = modificacion
                        
                        # Extraemos SOLO los casos base que sean números para este parámetro
                        bases_en_pos = {val for (pos, val) in self.pos_valor if pos == i and isinstance(val, (int, float))}
                        
                        if bases_en_pos:
                            # TRUCO: Si el salto es de tamaño 'paso', necesitamos al menos 'paso' casos base 
                            if len(bases_en_pos) < paso:
                                raise ValueError(
                                    f"Error de Terminación: "
                                    f"La llamada recursiva avanza de a {paso} en el parámetro {i}, "
                                    f"pero solo hay {len(bases_en_pos)} casos base numéricos definidos: {bases_en_pos}. "
                                    f"Podría saltarse el caso base y caer en recursión infinita."
                                )
                            else:
                                progresa = True # Demuestra que avanza hacia el caso base numérico

            if not progresa:
                 raise ValueError(
                    f"Posible Recursión Infinita: "
                    f"La llamada recursiva '{nodo.nombre}' no demuestra una métrica estrictamente decreciente "
                    f"hacia un caso base algebraico o numérico conocido."
                )

    def validar_y_anotar(self, nodo):
        """
        Recorre el árbol, valida que todo exista y anota los nodos Variable 
        con su tipo real para la futura generación de C++.
        """
        numericos = {'nat', 'int', 'real'}

        if isinstance(nodo, Numero):
            return "nat" 

        elif isinstance(nodo, Variable):
            tipo_en_tabla = self.locales.get(nodo.nombre) or self.globales.get(nodo.nombre)
            
            if not tipo_en_tabla:
                raise ValueError(f"Error Semántico: Variable '{nodo.nombre}' no declarada.")

            # Lógica iterativa para desenvolver Arrays (Matrices de N dimensiones)
            tipo_actual = tipo_en_tabla
            
            for i, idx in enumerate(nodo.indices):
                # Validamos primero el índice
                self.validar_y_anotar(idx) 
                
                # Pelamos una capa del tipo array
                if tipo_actual.startswith("array<"):
                    # Quitamos "array<" del principio y el ">" del final
                    contenido = tipo_actual[6:-1] 
                    
                    # Buscamos si hay un tamaño opcional ", N" para ignorarlo
                    nivel = 0
                    corte = len(contenido)
                    for j in range(len(contenido)-1, -1, -1):
                        if contenido[j] == '>': nivel += 1
                        elif contenido[j] == '<': nivel -= 1
                        elif contenido[j] == ',' and nivel == 0:
                            corte = j # Encontramos la coma del nivel superior
                            break
                    
                    tipo_actual = contenido[:corte].strip()
                else:
                    raise ValueError(
                        f"Error de Tipos: Se intentó indexar '{nodo.nombre}' demasiadas veces. "
                        f"No se puede indexar el tipo '{tipo_actual}'."
                    )

            # ANOTACIÓN: Guardamos el tipo final en el nodo
            nodo.tipo = tipo_actual
            
            return tipo_actual

        elif isinstance(nodo, OperacionBinaria):
            t_izq = self.validar_y_anotar(nodo.izq)
            t_der = self.validar_y_anotar(nodo.der)

            # 1. Operadores Aritméticos
            if nodo.operador in ('+', '-', '*', '/'):
                if t_izq not in numericos or t_der not in numericos:
                    raise ValueError(
                        f"Error de Tipos: El operador '{nodo.operador}' requiere operandos numéricos. "
                        f"Recibió '{t_izq}' y '{t_der}'."
                    )
                # Inferencia básica: si hay un real, el resultado es real. Si hay int, es int. Si no, nat.
                if 'real' in (t_izq, t_der): return 'real'
                if 'int' in (t_izq, t_der): return 'int'
                return 'nat'

            # 2. Operadores Relacionales (Comparaciones)
            elif nodo.operador in ('<', '<=', '>', '>=', '==', '!='):
                son_numericos = (t_izq in numericos) and (t_der in numericos)
                # Tienen que ser ambos numéricos, o ser exactamente del mismo tipo (ej. char == char)
                if not (son_numericos or t_izq == t_der):
                    raise ValueError(
                        f"Error de Tipos: No se puede comparar '{t_izq}' con '{t_der}' "
                        f"usando el operador '{nodo.operador}'."
                    )
                return 'bool' # Las comparaciones SIEMPRE generan un booleano

            # 3. Operadores Lógicos
            elif nodo.operador in ('and', 'or'):
                if t_izq != 'bool' or t_der != 'bool':
                    raise ValueError(
                        f"Error de Tipos: El operador '{nodo.operador}' requiere operandos booleanos. "
                        f"Recibió '{t_izq}' y '{t_der}'."
                    )
                return 'bool'

            # Fallback por si acaso
            return t_izq

        elif isinstance(nodo, Llamada):
            self.llamada(nodo) # Verifica la terminación y la recursividad
            for i, arg in enumerate(nodo.argumentos):
                tipo_arg = self.validar_y_anotar(arg)

                if tipo_arg not in numericos:
                        raise ValueError(
                            f"Error de Tipos: El parámetro {i+1} en la llamada a '{nodo.nombre}' "
                            f"debe ser numérico, pero se recibió '{tipo_arg}'."
                        )
            return "nat" # Asumimos que las llamadas a funciones DP devuelven un coste numérico

        elif isinstance(nodo, Reduccion):
            if nodo.rango:
                # CORRECCIÓN: Ahora locales es un diccionario, asignamos el iterador como 'nat'
                self.locales[nodo.rango.iterador.nombre] = "nat"
                self.validar_y_anotar(nodo.rango.limite_inf)
                self.validar_y_anotar(nodo.rango.limite_sup)
                
                # Apilamos la restricción matemática para el análisis relacional
                self.restricciones_activas.append(nodo.rango)
            
            for arg in nodo.argumentos:
                self.validar_y_anotar(arg)
            
            if nodo.rango:
                # Desapilamos al salir de la reducción
                self.restricciones_activas.pop()

            return "nat"

    def ecuacion(self, eq):
        lhs = eq.izq
        rhs = eq.der
        cond = eq.condicion
        
        self.comprobacionFunc(lhs.nombre, "lado izquierdo de ecuación")
        self.locales.clear() # .clear() funciona perfectamente tanto en dicts como sets
        
        variables_vistas = {}
        
        # 1. Analizar parámetros buscando números o variables repetidas
        for i, param in enumerate(lhs.argumentos):
            if isinstance(param, Variable):
                if param.nombre in variables_vistas:
                    pos_anterior = variables_vistas[param.nombre]
                    self.relaciones_base.add(('==', pos_anterior, i))
                else:
                    variables_vistas[param.nombre] = i
                    # CORRECCIÓN: locales es un dict. Asumimos que los parámetros DP son numéricos por defecto.
                    self.locales[param.nombre] = "nat" 
                    
            elif isinstance(param, Numero):
                self.pos_valor.add((i, param.valor))

        # 2. Analizar condiciones (ej: if i == j)
        if cond and isinstance(cond, OperacionBinaria) and cond.operador == '==':
            if isinstance(cond.izq, Variable) and isinstance(cond.der, Variable):
                if cond.izq.nombre in variables_vistas and cond.der.nombre in variables_vistas:
                    pos_izq = variables_vistas[cond.izq.nombre]
                    pos_der = variables_vistas[cond.der.nombre]
                    self.relaciones_base.add(('==', pos_izq, pos_der))

        # 3. Validar variables y estructura
        if eq.es_caso_base:
            self.casos_base.append(eq)
        else:  
            self.is_rhs = True
            self.validar_y_anotar(rhs) # CORRECCIÓN: Usamos la función unificada
            if cond:
                self.validar_y_anotar(cond) # CORRECCIÓN: Usamos la función unificada
            self.is_rhs = False

    def inicial(self, retorno):
        self.comprobacionFunc(retorno.nombre, "retorno inicial")
        self.validar_y_anotar(retorno)    
            
    # --- FUNCIONES MATEMÁTICAS DE CONVERGENCIA ---

    def _verifica_convergencia_relacional(self, nodo_llamada):
        """
        Verifica algebraicamente si la distancia entre parámetros disminuye
        evaluando si los argumentos forman un subintervalo estricto del rango activo.
        """
        if not self.relaciones_base or not self.restricciones_activas:
            return False

        rango = self.restricciones_activas[-1]
        iterador = rango.iterador

        for relacion in self.relaciones_base:
            if relacion[0] == '==':
                pos1, pos2 = relacion[1], relacion[2]
                
                arg1 = nodo_llamada.argumentos[pos1]
                arg2 = nodo_llamada.argumentos[pos2]

                es_subintervalo_izq = self._evaluar_limite(arg1, rango.limite_inf) and \
                                      (self._evaluar_limite(arg2, iterador) or self._evaluar_progreso(arg2, iterador))

                es_subintervalo_der = (self._evaluar_limite(arg1, iterador) or self._evaluar_progreso(arg1, iterador)) and \
                                      self._evaluar_limite(arg2, rango.limite_sup)

                if es_subintervalo_izq or es_subintervalo_der:
                    return True

        return False

    def _evaluar_limite(self, arg, limite):
        """Comprueba la equivalencia directa entre dos objetos Variable."""
        if isinstance(arg, Variable) and isinstance(limite, Variable):
            return arg.nombre == limite.nombre
        return False

    def _evaluar_progreso(self, arg, iterador):
        """
        Detecta si el argumento avanza o retrocede respecto al iterador (ej. k + 1).
        Ambos son objetos Variable.
        """
        if isinstance(arg, OperacionBinaria) and arg.operador in ('+', '-'):
            # CAMBIO AQUÍ: comparamos con iterador.nombre
            izq_es_iter = isinstance(arg.izq, Variable) and arg.izq.nombre == iterador.nombre
            der_es_iter = isinstance(arg.der, Variable) and arg.der.nombre == iterador.nombre
            
            izq_es_const = isinstance(arg.izq, Numero) and arg.izq.valor > 0
            der_es_const = isinstance(arg.der, Numero) and arg.der.valor > 0
            
            if arg.operador == '-':
                return izq_es_iter and der_es_const
            else:
                return (izq_es_iter and der_es_const) or (der_es_iter and izq_es_const)
                
        return False   
        

def validar_entrada(codigo: str):
    # sintactica
    try:
        tree_lark = parser.parse(codigo)
    except UnexpectedInput as e:
        context = e.get_context(codigo)
        return False, f"[Sintaxis] L{e.line}:{e.column} cerca de -> {context.strip()}"

    tree = IRBuilder().transform(tree_lark)
    # semantica
    checker = SemanticChecks()
    
    try:
        checker.validar_programa(tree)
    except ValueError as semerr:
        return False, str(semerr)

    return True, "Sintaxis y semantica correctas"


if __name__ == "__main__":
    entrada =  """ nat N;
                nat W;
                array<nat> v, w;

                mochila(0, c) = 0;
                mochila(i, 0) = 0;
                mochila(i, c) = mochila(i - 1, c) if w[i] > c;
                mochila(i, c) = max{ mochila(i - 1, c), v[i] + mochila(i - 1, c - w[i]) } if w[i] <= c;

                return mochila(N, W); """
    
    """ nat N;
                array<nat> d;

                secMatrices(i, i) = 0;
                secMatrices(i, j) = min{i <= k < j}( secMatrices(i, k) + secMatrices(k + 1,j) + d[i - 1] * d[k] * d[j] );

                return secMatrices(1, N); """
    
    """ nat N, M;
                    array<char> A, B;

                    LCS(i, 0) = 0;
                    LCS(0, j) = 0;
                    LCS(i, j) = LCS(i-1, j-1) + 1 if A[i] == B[j];
                    LCS(i, j) = max{ LCS(i - 1, j), LCS(i, j-1) } if A[i] != B[j];
                    
                    return LCS(N, M);"""
    
    """nat F, C;
                    array<array<nat>> coste;

                    camino(1, 1) = coste[1][1];
                    camino(i, 1) = camino(i - 1, 1) + coste[i][1] if i > 1;
                    camino(1, j) = camino(1, j - 1) + coste[1][j] if j > 1;
                    camino(i, j) = min{ camino(i - 1, j), camino(i, j - 1) } + coste[i][j] if i > 1 and j > 1;

                    return camino(F, C);"""
    
    """//
        // Números combinatorios / coeficientes binomiales
        

        nat N, K;  // calculamos N sobre K

        // precondición K <= N, ¿expresarlo en el lenguaje?
        
        binom(0, k) = 0;
        binom(n, 0) = 1;
        binom(n, k) = binom(n - 1, k - 1) + binom(n - 1, k);

        return binom(N, K);"""

    
    
    """
        nat N; 

        // Factorial: fact(n) = n * fact(n - 1)
        fact(0) = 1;
        fact(n) = n * fact(n - 1);

        return fact(N);
    """

    # comprobar correcteza de la funcion
    ok, msg = validar_entrada(entrada)
    print(msg)

    # imprimir codigo de funcion recursiva
    if ok:
        tree = parser.parse(entrada)
        builder = IRBuilder()
        codigo = builder.transform(tree)
        import pprint 
        pprint.pprint(codigo)

