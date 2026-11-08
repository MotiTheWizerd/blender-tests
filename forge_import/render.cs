var names = new[] { "ShortSword", "ArmingSword", "HuntingBow", "RecurveBow", "Quiver", "Arrow", "BroadheadArrow" };
var scene = UnityEditor.SceneManagement.EditorSceneManager.NewPreviewScene();
try {
var outDir = @"C:\Users\User\AppData\Local\Temp\oga\renders";
System.IO.Directory.CreateDirectory(outDir);
var camGo = new GameObject("cam"); UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(camGo, scene);
var cam = camGo.AddComponent<Camera>(); cam.scene = scene; cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = new Color(0.22f,0.24f,0.27f); cam.fieldOfView = 30;
var lightGo = new GameObject("sun"); UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(lightGo, scene);
var light = lightGo.AddComponent<Light>(); light.type = LightType.Directional; light.intensity = 1.6f; lightGo.transform.rotation = Quaternion.Euler(40, -30, 0);
var fillGo = new GameObject("fill"); UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(fillGo, scene);
var fill = fillGo.AddComponent<Light>(); fill.type = LightType.Directional; fill.intensity = 0.6f; fillGo.transform.rotation = Quaternion.Euler(20, 150, 0);
var rt = new RenderTexture(800, 800, 24); cam.targetTexture = rt;
var report = new System.Text.StringBuilder();
foreach (var n in names) {
  var prefab = UnityEditor.AssetDatabase.LoadAssetAtPath<GameObject>($"Assets/_Project/Content/Models/{n}/{n}.prefab");
  foreach (var view in new[] { "rest", "held" }) {
    var go = (GameObject)UnityEditor.PrefabUtility.InstantiatePrefab(prefab, scene);
    if (view == "held") { var inner = go.transform.GetChild(0); go.transform.rotation = Quaternion.Inverse(inner.localRotation); go.transform.position = -(go.transform.rotation * inner.localPosition); }
    var b = new Bounds(go.transform.position, Vector3.zero); foreach (var r in go.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
    var d = b.extents.magnitude / Mathf.Tan(15 * Mathf.Deg2Rad) * 1.05f;
    var dir = view == "rest" ? new Vector3(0.5f, 0.8f, -0.6f).normalized : new Vector3(0.35f, 0.25f, -1f).normalized;
    cam.transform.position = b.center + dir * d; cam.transform.LookAt(b.center); cam.nearClipPlane = 0.01f; cam.farClipPlane = d * 4;
    cam.Render();
    RenderTexture.active = rt; var tex = new Texture2D(800, 800, TextureFormat.RGB24, false); tex.ReadPixels(new Rect(0,0,800,800),0,0); tex.Apply(); RenderTexture.active = null;
    System.IO.File.WriteAllBytes($@"{outDir}\{n}_{view}.png", tex.EncodeToPNG()); UnityEngine.Object.DestroyImmediate(tex);
    report.AppendLine($"{n} {view}: size {b.size.ToString("F3")} center {b.center.ToString("F3")}");
    UnityEngine.Object.DestroyImmediate(go);
  }
}
cam.targetTexture = null; UnityEngine.Object.DestroyImmediate(rt);
return report.ToString();
} finally { UnityEditor.SceneManagement.EditorSceneManager.ClosePreviewScene(scene); }
