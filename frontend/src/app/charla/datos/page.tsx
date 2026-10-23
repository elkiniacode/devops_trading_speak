/**
 * Draft data-treatment policy (Ley 1581 de 2012, Decreto 1377 de 2013) for the live talk.
 * Static text only; pending legal review, hence the amber badge.
 */
export default function DatosPage() {
  return (
    <main className="c-doc">
      <a href="/charla/" className="c-btn-link" style={{ alignSelf: "flex-start", paddingLeft: 0 }}>
        ← Volver a la charla
      </a>
      <span className="c-badge-amber" style={{ alignSelf: "flex-start" }} data-testid="datos-draft">
        BORRADOR · PENDIENTE DE REVISIÓN
      </span>
      <h1 className="holo">Política de tratamiento de datos</h1>
      <p>
        Charla «Agentic Engineering», viernes 23 de octubre de 2026, Bogotá. Este texto explica qué datos pedimos
        durante la charla, para qué los usamos y cómo ejercer tus derechos según la Ley 1581 de 2012 y el Decreto 1377
        de 2013.
      </p>

      <section>
        <h2>Responsable</h2>
        <p>
          <strong>IA Revolutions</strong> (Elkin Camargo Patarroyo), Bogotá, Colombia. Para cualquier solicitud sobre
          tus datos escribe al correo desde el que recibiste el enlace de entrada.
        </p>
      </section>

      <section>
        <h2>Qué datos recogemos</h2>
        <ul>
          <li>
            <strong>Nombre de usuario y correo:</strong> para enviarte el enlace de entrada a la sala y mostrar tu
            nombre en el ranking.
          </li>
          <li>
            <strong>Respuestas:</strong> las opciones que eliges en el quiz, el tiempo que tardas y tu respuesta a la
            pregunta abierta.
          </li>
          <li>
            <strong>Celular (opcional):</strong> solo si lo escribes y autorizas que te contactemos por WhatsApp.
          </li>
        </ul>
      </section>

      <section>
        <h2>Para qué los usamos</h2>
        <ul>
          <li>Darte acceso a la sala y calcular tu puntaje y tu puesto.</li>
          <li>
            Mostrar en pantalla resultados agregados y algunas respuestas abiertas con tu nombre de usuario. El
            presentador puede ocultar cualquier respuesta o nombre.
          </li>
          <li>Clasificar por tema las respuestas abiertas con un modelo de IA. Solo se envía el texto de la respuesta.</li>
          <li>
            Si lo autorizas: enviarte por WhatsApp tu resultado, las diapositivas y novedades de IA Revolutions.
          </li>
        </ul>
      </section>

      <section>
        <h2>Tus derechos</h2>
        <p>
          Puedes conocer, actualizar, rectificar y pedir que borremos tus datos, y revocar la autorización en cualquier
          momento. Responderemos dentro de los plazos de la ley (10 días hábiles para consultas y 15 para reclamos).
          También puedes acudir a la Superintendencia de Industria y Comercio.
        </p>
      </section>

      <section>
        <h2>Conservación</h2>
        <p>
          Guardamos los datos solo el tiempo necesario para las finalidades anteriores. No los vendemos ni los
          compartimos con terceros para su propio uso.
        </p>
      </section>
    </main>
  );
}
