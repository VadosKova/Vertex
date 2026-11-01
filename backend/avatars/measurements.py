SPEC = {
    "head_circumference": ("head_neck", 48, 66, "Стрічка по лобі над бровами та навколо потилиці", "Tape across the forehead above the brows and around the back of the head"),
    "face_length": ("head_neck", 15, 27, "Від лінії росту волосся до підборіддя", "Hairline to chin"),
    "face_width": ("head_neck", 10, 18, "Між виличними кістками", "Between the cheekbones"),
    "neck_circumference": ("head_neck", 28, 50, "Біля основи шиї, стрічка не тисне", "Around the base of the neck, tape not tight"),
    "shoulder_width": ("torso", 30, 60, "Між кістковими точками плечей ззаду", "Between the shoulder bone points across the back"),
    "chest_circumference": ("torso", 60, 160, "По найвищих точках грудей, стрічка паралельна підлозі", "Over the fullest part of the chest, tape parallel to the floor"),
    "underbust_circumference": ("torso", 55, 140, "Одразу під грудьми", "Directly under the bust"),
    "waist_circumference": ("torso", 45, 160, "У найвужчому місці тулуба", "At the narrowest part of the torso"),
    "abdomen_circumference": ("torso", 50, 170, "На рівні пупка / нижнього преса", "At navel level / lower abdomen"),
    "torso_length": ("torso", 30, 60, "Від сьомого шийного хребця до талії", "C7 vertebra to the waist"),
    "arm_length": ("arms", 45, 80, "Від плечового суглоба до зап'ястя", "Shoulder joint to wrist"),
    "bicep_relaxed": ("arms", 18, 50, "Найширше місце плеча, рука розслаблена", "Widest part of the upper arm, relaxed"),
    "bicep_flexed": ("arms", 20, 55, "Те саме з напруженим біцепсом", "Same with the biceps flexed"),
    "forearm_circumference": ("arms", 17, 40, "Найширше місце передпліччя", "Widest part of the forearm"),
    "wrist_circumference": ("arms", 10, 24, "Над кісточкою зап'ястя", "Just above the wrist bone"),
    "hip_circumference": ("lower", 70, 170, "По найвипнутіших точках сідниць", "Over the fullest part of the buttocks"),
    "inseam": ("lower", 55, 100, "Внутрішній шов: від паху до кісточки", "Crotch to ankle bone"),
    "outseam": ("lower", 80, 130, "Зовнішній шов: від талії до підлоги", "Waist to floor along the outer leg"),
    "thigh_circumference": ("lower", 35, 95, "У верхній третині стегна", "Upper third of the thigh"),
    "knee_circumference": ("lower", 25, 55, "Навколо коліна", "Around the knee"),
    "calf_circumference": ("lower", 25, 60, "Найширше місце литки", "Widest part of the calf"),
    "ankle_circumference": ("lower", 15, 35, "Над кісточкою", "Just above the ankle bone"),
    "foot_length": ("foot", 20, 33, "Від п'яти до найдовшого пальця", "Heel to the longest toe"),
    "foot_width": ("foot", 7, 14, "У найширшому місці стопи", "Widest part of the foot"),
}

REQUIRED = ("chest_circumference", "waist_circumference", "hip_circumference")

HEIGHT_RANGE = (120, 230)
WEIGHT_RANGE = (30, 250)
AGE_RANGE = (12, 100)

_RATIOS = {
    "shoulder_width": (0.259, 0.230),
    "neck_circumference": (0.215, 0.185),
    "torso_length": (0.300, 0.290),
    "arm_length": (0.330, 0.320),
    "inseam": (0.450, 0.450),
    "outseam": (0.600, 0.600),
    "head_circumference": (0.325, 0.315),
    "foot_length": (0.150, 0.145),
    "foot_width": (0.057, 0.054),
}