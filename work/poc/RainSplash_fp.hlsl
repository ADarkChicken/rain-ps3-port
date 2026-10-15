// Custom/RainSplash — fragment program, translated from RSX microcode (work/poc/RainSplash.fp.asm.txt).
// ShaderLab state (kept from asset text): Tags Queue=Transparent-200, ZWrite Off, Cull Off, Fog Off, Blend SrcAlpha One.
// Texture units from ShaderLab: SetTexture 0 [_MainTex], SetTexture 1 [_MaskTex].
// Inputs tc0/tc1/diff_color come from the vertex program (VP not yet decoded: tc1 semantics = projective coords, INFERENCE).
sampler2D _MainTex : register(s0);
sampler2D _MaskTex : register(s1);

struct PSIn
{
    float4 color : COLOR0;     // diff_color
    float4 tc0   : TEXCOORD0;  // tc0
    float4 tc1   : TEXCOORD1;  // tc1
};

float4 main(PSIn i) : COLOR0
{
    float  r0x = tex2Dproj(_MaskTex, i.tc1).x;      // 0: TXP R0.x, tc1, tex1
    half   h2x = (r0x >= 1.0) ? 1.0 : 0.0;          // 1: SGE H2.x, R0.x, c(1.0)   (half precision dest)
    float4 r0  = tex2D(_MainTex, i.tc0.xy);         // 3: TEX R0, tc0, tex0
    float4 r2  = r0 * i.color;                      // 4: MUL R2, R0, diff_color
    half4  h0;
    h0.w   = r2.w * h2x;                            // 5: MUL H0.w, R2, H2.xxxx
    h0.xyz = r2.xyz;                                // 6: MOV H0.xyz, R2   (H0 = color output), END
    return h0;
}
