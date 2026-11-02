// Put this file in Assets/Editor/ (any folder named Editor). It runs every time Unity imports a model.
// Any child whose name ends in "_COL" becomes an invisible convex MeshCollider:
// it shapes the physics, it is never drawn.
using UnityEditor;
using UnityEngine;

public class SwordImportSetup : AssetPostprocessor
{
    void OnPostprocessModel(GameObject root)
    {
        foreach (var t in root.GetComponentsInChildren<Transform>(true))
        {
            if (!t.name.EndsWith("_COL")) continue;
            var filter = t.GetComponent<MeshFilter>();
            if (filter == null) continue;
            var collider = t.gameObject.AddComponent<MeshCollider>();
            collider.sharedMesh = filter.sharedMesh;
            collider.convex = true;                       // required for a collider on a moving Rigidbody
            Object.DestroyImmediate(t.GetComponent<MeshRenderer>());
            Object.DestroyImmediate(filter);
        }
    }
}
