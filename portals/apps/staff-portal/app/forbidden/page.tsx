export default function Forbidden() {
  return (
    <div className="card stack" style={{ maxWidth: 560 }}>
      <h1 style={{ margin: 0 }}>Not permitted</h1>
      <p style={{ margin: 0 }}>Your role does not allow this action. The attempt has been recorded.</p>
      <a className="btn" href="/">Back</a>
    </div>
  );
}
