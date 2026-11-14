
from lib.window_arena import *
from lib.winobj_ship import *
from typing import List
import math
import time


def updateShipMohamed(ship: Ship, powerUps: List[PowerUp], targets: List[Target]):
    ship.setPlayerName("Karim M")

    # ---------------- SETTINGS ----------------
    BULLET_SPEED = 8.0
    MAX_MOVE = 8.0
    WALL_MARGIN = 0.8
    PREFERRED_RANGE = 5.5
    ENDGAME_BUFFER = 0.3

    timeLeft = max(0.0, ship.window.levelTime)
    enemy = ship.getOther()

    maxX = ship.window.maxCoordinateX()
    maxY = ship.window.maxCoordinateY()

    # ---------------- SCORE AWARENESS ----------------
    scores = ship.window.levelScores
    myScore = scores[ship.playerIdx]
    enemyScore = scores[1 - ship.playerIdx]

    scoreDifference = myScore - enemyScore

    urgency = 0.0
    if scoreDifference < 0:
        urgency = min(1.0, abs(scoreDifference) / 100.0)

    # ---------------- HELPERS ----------------
    def clamp(value, low, high):
        return max(low, min(high, value))

    def distance(a, b):
        return length(b - a)

    def objectAvailable(obj):
        return getattr(obj, "timeTillDeath", 0) <= 0

    def turnNeeded(facing, direction):
        if length(direction) < 0.0001:
            return 0.0

        angle = angleDeg(direction) - angleDeg(facing)

        while angle > 180:
            angle -= 360

        while angle < -180:
            angle += 360

        return angle

    def turnTime(someShip, spot):
        if someShip.shipTurnSpeed <= 0:
            return 1000.0

        angle = turnNeeded(someShip.dir, spot - someShip.pos)

        return abs(angle) / someShip.shipTurnSpeed

    def travelTime(someShip, spot):
        if someShip.shipMoveSpeed <= 0:
            return 1000.0

        return (
            turnTime(someShip, spot)
            + distance(someShip.pos, spot) / someShip.shipMoveSpeed
        )

    def clampPosition(spot):
        return v2(
            clamp(spot[0], WALL_MARGIN, maxX - WALL_MARGIN),
            clamp(spot[1], WALL_MARGIN, maxY - WALL_MARGIN)
        )

    def onScreen(spot):
        return (
            WALL_MARGIN < spot[0] < maxX - WALL_MARGIN
            and WALL_MARGIN < spot[1] < maxY - WALL_MARGIN
        )

    # ---------------- MOVEMENT ----------------
    def flyTo(spot):
        spot = clampPosition(spot)

        direction = spot - ship.pos
        dist = length(direction)

        if dist < 0.4:
            return False

        angle = turnNeeded(ship.dir, direction)

        if angle > 1.0:
            ship.queueCommand(ShipCmd_ThrustRight(angle))
        elif angle < -1.0:
            ship.queueCommand(ShipCmd_ThrustLeft(-angle))

        moveBy = min(dist, MAX_MOVE)

        if moveBy > 0.3:
            ship.queueCommand(ShipCmd_Thrust(moveBy))
            return True

        return False

    # ---------------- PROJECTILE INTERCEPTION ----------------
    def solveProjectileTime(relativePosition, targetVelocity):
        a = dot(targetVelocity, targetVelocity) - BULLET_SPEED ** 2
        b = 2.0 * dot(relativePosition, targetVelocity)
        c = dot(relativePosition, relativePosition)

        if abs(a) < 0.00001:
            if abs(b) < 0.00001:
                return None

            result = -c / b

            if result > 0.001:
                return result

            return None

        discriminant = b * b - 4.0 * a * c

        if discriminant < 0:
            return None

        root = math.sqrt(discriminant)

        t1 = (-b - root) / (2.0 * a)
        t2 = (-b + root) / (2.0 * a)

        validTimes = [t for t in (t1, t2) if t > 0.001]

        if not validTimes:
            return None

        return min(validTimes)

    def calculateIntercept(target):
        targetPos = target.pos
        targetVel = target.vel

        aim = targetPos
        projectileTime = 0.0
        turningDuration = 0.0

        # Estimate the target's position when the ship finishes turning.
        for _ in range(10):
            turningDuration = turnTime(ship, aim)

            futureTargetAtLaunch = (
                targetPos + targetVel * turningDuration
            )

            relativePosition = futureTargetAtLaunch - ship.pos

            projectileTime = solveProjectileTime(
                relativePosition,
                targetVel
            )

            if projectileTime is None:
                return None

            newAim = targetPos + targetVel * (
                turningDuration + projectileTime
            )

            if distance(aim, newAim) < 0.01:
                aim = newAim
                break

            aim = newAim

        # Final calculation using the updated aim point.
        turningDuration = turnTime(ship, aim)

        futureTargetAtLaunch = (
            targetPos + targetVel * turningDuration
        )

        projectileTime = solveProjectileTime(
            futureTargetAtLaunch - ship.pos,
            targetVel
        )

        if projectileTime is None:
            return None

        aim = targetPos + targetVel * (
            turningDuration + projectileTime
        )

        shotDistance = BULLET_SPEED * projectileTime

        if shotDistance > ship.ammoMaxRange:
            return None

        if not onScreen(aim):
            return None

        return aim, projectileTime, turningDuration

    # ---------------- SHOT EVALUATION ----------------
    def evaluateShot(target, reward, baseConfidence, effectiveRadius):
        if target is None:
            return None

        # Ships do not have timeTillDeath, so check safely.
        if not objectAvailable(target):
            return None

        result = calculateIntercept(target)

        if result is None:
            # Direct aiming is acceptable for stationary targets.
            if length(target.vel) > 0.05:
                return None

            aim = target.pos
            shotDistance = distance(ship.pos, aim)

            if shotDistance < 0.001:
                return None

            if shotDistance > ship.ammoMaxRange:
                return None

            projectileTime = shotDistance / BULLET_SPEED
            turningDuration = turnTime(ship, aim)

        else:
            aim, projectileTime, turningDuration = result

        totalTime = turningDuration + projectileTime

        if totalTime + ENDGAME_BUFFER >= timeLeft:
            return None

        if not onScreen(aim):
            return None

        angle = abs(turnNeeded(ship.dir, aim - ship.pos))

        # Shooting can insert a separate turning command.
        needsTurnCommand = angle > 2.6

        commandCost = 2.0

        if needsTurnCommand:
            commandCost += 1.0

        # Approximate collision reliability.
        sizeConfidence = clamp(
            effectiveRadius / 0.55,
            0.30,
            1.0
        )

        confidence = baseConfidence * sizeConfidence

        # Longer shots have more opportunity for prediction error.
        rangeFraction = (
            BULLET_SPEED * projectileTime
            / max(ship.ammoMaxRange, 0.001)
        )

        confidence *= 1.0 - 0.10 * rangeFraction
        confidence = clamp(confidence, 0.10, 0.99)

        expectedPoints = reward * confidence
        netExpectedPoints = expectedPoints - commandCost

        # Score urgency slightly favors scoring opportunities
        # when we are behind, especially near the end.
        strategicPoints = expectedPoints

        if scoreDifference < 0:
            lateGameFactor = max(0.0, 1.0 - timeLeft / 90.0)

            strategicPoints *= (
                1.0 + urgency * lateGameFactor * 0.15
            )

        utility = (
            strategicPoints - commandCost
        ) / (0.45 + totalTime)

        return {
            "aim": aim,
            "utility": utility,
            "expected": expectedPoints,
            "net": netExpectedPoints,
            "time": totalTime,
            "confidence": confidence
        }

    # ---------------- 1. FIND BEST SHOT ----------------
    bestShot = None
    bestShotUtility = -100000.0

    cooldown = max(
        0.0,
        1.0 - (time.time() - ship.timeLastShot)
    )

    if ship.ammo > 0 and cooldown <= 0:
        # Evaluate ordinary targets.
        for target in targets:
            if not objectAvailable(target):
                continue

            moving = (
                length(target.vel) > 0.001
            )

            if moving:
                effectiveRadius = target.radius * (2.0 / 3.0) + 0.15
                baseConfidence = 0.96
            else:
                effectiveRadius = target.radius + 0.15
                baseConfidence = 0.98

            shot = evaluateShot(
                target,
                reward=20.0,
                baseConfidence=baseConfidence,
                effectiveRadius=effectiveRadius
            )

            if shot is not None:
                if shot["utility"] > bestShotUtility:
                    bestShot = shot
                    bestShotUtility = shot["utility"]

        # Evaluate the opposing ship.
        if enemy is not None:
            enemySpeed = length(enemy.vel)

            enemyConfidence = (
                0.78 if enemySpeed < 0.5 else 0.66
            )

            enemyShot = evaluateShot(
                enemy,
                reward=25.0,
                baseConfidence=enemyConfidence,
                effectiveRadius=0.40
            )

            if enemyShot is not None:
                enemyUtility = enemyShot["utility"]

                if scoreDifference < 0:
                    enemyUtility *= 1.0 + urgency * 0.12

                if enemyUtility > bestShotUtility:
                    bestShot = enemyShot
                    bestShotUtility = enemyUtility

    # ---------------- 2. EVALUATE POWERUPS ----------------
    bestPowerUp = None
    bestPowerUpUtility = -100000.0

    remainingFraction = clamp(timeLeft / 90.0, 0.0, 1.0)

    if timeLeft > 2.0:
        for powerUp in powerUps:
            if not objectAvailable(powerUp):
                continue

            myTime = travelTime(ship, powerUp.pos)

            if myTime + ENDGAME_BUFFER >= timeLeft:
                continue

            # Avoid chasing pickups the enemy should reach first.
            if enemy is not None:
                enemyTime = travelTime(enemy, powerUp.pos)

                if enemyTime + 0.6 < myTime:
                    continue

            benefit = 0.0

            if powerUp.type in ("1", "2", "3"):
                amount = int(powerUp.type)

                if ship.ammo == 0:
                    valuePerAmmo = 15.0
                elif ship.ammo <= 2:
                    valuePerAmmo = 11.0
                elif ship.ammo <= 5:
                    valuePerAmmo = 7.0
                else:
                    valuePerAmmo = 3.0

                benefit = amount * valuePerAmmo

            elif powerUp.type == "S":
                benefit = 17.0 * (remainingFraction ** 0.8)

            elif powerUp.type == "R":
                benefit = 12.0 * (remainingFraction ** 0.8)

            else:
                continue

            movementCost = 2.0

            if myTime > 5.0:
                movementCost += 1.0

            netBenefit = benefit - movementCost

            utility = netBenefit / (0.8 + myTime)

            if ship.ammo == 0 and powerUp.type in ("1", "2", "3"):
                utility *= 1.35

            # Upgrades are less valuable near the end.
            if powerUp.type in ("S", "R"):
                utility *= remainingFraction

            if utility > bestPowerUpUtility:
                bestPowerUpUtility = utility
                bestPowerUp = powerUp

    # ---------------- 3. CHOOSE SHOT OR POWERUP ----------------
    if bestShot is not None:
        if bestPowerUp is None or bestShotUtility >= bestPowerUpUtility:
            ship.queueCommand(
                ShipCmd_Shoot(bestShot["aim"] - ship.pos)
            )
            return

    if bestPowerUp is not None and bestPowerUpUtility >= 1.5:
        if flyTo(bestPowerUp.pos):
            return

    # ---------------- 4. POSITIONING ----------------
    if ship.ammo > 0 and timeLeft > 3.0:
        bestDestination = None
        bestPositionUtility = -100000.0

        for target in targets:
            if not objectAvailable(target):
                continue

            currentDistance = distance(ship.pos, target.pos)

            estimatedTime = currentDistance / max(
                ship.shipMoveSpeed,
                0.001
            )

            futureTarget = target.pos + target.vel * estimatedTime

            toTarget = futureTarget - ship.pos
            futureDistance = length(toTarget)

            if futureDistance < 0.001:
                continue

            desiredRange = min(
                PREFERRED_RANGE,
                ship.ammoMaxRange * 0.65
            )

            if futureDistance <= desiredRange + 0.8:
                continue

            destination = (
                futureTarget - unit(toTarget) * desiredRange
            )

            destination = clampPosition(destination)

            movementTime = travelTime(ship, destination)

            if movementTime + ENDGAME_BUFFER >= timeLeft:
                continue

            positionUtility = (
                futureDistance - desiredRange
            ) / (1.0 + movementTime)

            if positionUtility > bestPositionUtility:
                bestPositionUtility = positionUtility
                bestDestination = destination

        if bestDestination is not None:
            flyTo(bestDestination)
            return

    # ---------------- 5. FALLBACK ----------------
    return


####################################################################################################
############################## DO NOT MODIFY METHODS BELOW THIS LINE ##############################
########################## EXCEPT TO REMOVE TUTORIAL GAME CONFIG ARGUMENT #########################
####################################################################################################

WindowArena(
    userCode1=updateShipMohamed,
    gameConfig=WindowArenaConfig.SPACE_BATTLE,
    windowTitle="TSA@RHS: Space Battle V3!"
).runGameLoop()
